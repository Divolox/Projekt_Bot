import requests
import time
import sys
import os
from datetime import datetime, timedelta

# ==============================================================================
# 🚀 SKANER HYBRYDOWY V10.3 (FIX: CENA 0.00001 + KOMENTARZE)
# ==============================================================================

# --- 1. INTEGRACJA Z BAZĄ DANYCH ---
current_dir = os.path.dirname(os.path.abspath(__file__)) 
parent_dir = os.path.dirname(current_dir)              
sys.path.append(parent_dir)
os.chdir(parent_dir)

try:
    import portfel_manager as pm
    from database_handler import DatabaseHandler
except ImportError:
    print("❌ BŁĄD KRYTYCZNY: Brak modułów bazy/portfela w folderze nadrzędnym!")
    sys.exit()

db = DatabaseHandler()

# --- 2. KONFIGURACJA STRATEGII ---
MIN_VOL_24H = 450000 

# [FIX] CENA MINIMALNA: 0.00001
# Eliminuje BTTC (0.000001), ale zostawia BONK (0.00002) i 1000SATS (0.0002)
MIN_CENA = 0.00001 

MAX_POZYCJI_SKANERA = 7 
INTERVAL_SKANOWANIA_NOWYCH = 300 # 5 minut
INTERVAL_OCHRONY = 10            # 10 sekund
COOLDOWN_CZAS = 3600      

# [FIX] Podniesiony próg do 3.5%, żeby ominąć szum, gdy BTC rośnie
CFG_AGRESYWNY = { "PRÓG": 3.5, "RSI": 88, "NAZWA": "🔥 AGRESYWNY (Pon-Sob)" }
CFG_BEZPIECZNY = { "PRÓG": 2.8, "RSI": 75, "NAZWA": "🛡️ BEZPIECZNY (Niedziela)" }

BAN_DNI = 3      # Ile dni bana za stratę
PROG_ACCEL = 0.0 # Przyspieszenie musi być dodatnie (nie hamujemy)

# Pamięć podręczna do fizyki (nie obciąża bazy ani API)
historia_cen_local = {} 

def pobierz_konfiguracje():
    return CFG_BEZPIECZNY if datetime.today().weekday() == 6 else CFG_AGRESYWNY

def get_binance_prices():
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        resp = requests.get(url, timeout=15).json()
        return {x['symbol']: x for x in resp if x['symbol'].endswith('USDT')}
    except: return {}

def get_kline_rsi(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=20"
        resp = requests.get(url, timeout=15).json()
        closes = [float(x[4]) for x in resp]
        deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]
        if not gains: return 0
        if not losses: return 100
        avg_gain = sum(gains) / len(gains)
        avg_loss = sum(losses) / len(losses)
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    except: return 50

# --- POMOCNICZE FUNKCJE SQL ---
def pobierz_pozycje_skanera_z_bazy():
    """Pobiera aktywne pozycje skanera z bazy danych"""
    try:
        db.cursor.execute("SELECT unikalne_id, symbol, cena_wejscia, czas_wejscia, max_zysk FROM aktywne_pozycje WHERE zrodlo='SKANER'")
        rows = db.cursor.fetchall()
        pozycje_dict = {}
        for r in rows:
            uid, sym, cena, czas, max_z = r
            pozycje_dict[sym] = {
                'unikalne_id': uid,
                'symbol': sym,
                'cena_wejscia': cena,
                'czas_zakupu': czas, 
                'max_zysk': max_z
            }
        return pozycje_dict
    except Exception as e:
        print(f"⚠️ Błąd SQL w Skanerze: {e}")
        return {}

# --- [FIX] USZCZELNIONA CZARNA LISTA ---
def czy_na_czarnej_liscie(symbol):
    """
    Sprawdza, czy coin przyniósł stratę w ostatnich 3 dniach.
    FIX: Uwzględnia też wpisy z NULL w dacie wyjścia (dla bezpieczeństwa).
    """
    try:
        data_graniczna = (datetime.now() - timedelta(days=BAN_DNI)).timestamp()
        
        # Zapytanie szuka strat (-0.1% lub gorzej)
        # Warunek: Data wyjścia > granica LUB Data wyjścia jest NULL (błąd zapisu = BAN)
        query = """
            SELECT count(*) FROM historia_transakcji 
            WHERE symbol = ? 
            AND zysk_proc < -0.1 
            AND (czas_wyjscia > ? OR czas_wyjscia IS NULL)
        """
        db.cursor.execute(query, (symbol, data_graniczna))
        count = db.cursor.fetchone()[0]
        
        if count > 0:
            return True
        return False
    except Exception as e:
        # W razie błędu bazy - logujemy, ale nie przerywamy działania
        return False

# --- FIZYKA (PRZYSPIESZENIE) ---
def oblicz_przyspieszenie(symbol, current_price):
    """Oblicza czy cena przyspiesza (acceleration > 0)"""
    teraz = time.time()
    if symbol not in historia_cen_local:
        historia_cen_local[symbol] = []
    
    historia_cen_local[symbol].append({"c": current_price, "t": teraz})
    # Trzymamy historię z 4 minut
    historia_cen_local[symbol] = [x for x in historia_cen_local[symbol] if teraz - x['t'] < 240]
    
    dane = historia_cen_local[symbol]
    if len(dane) < 3: return 0.1 
    
    p_teraz = dane[-1]['c']
    p_1min = next((x['c'] for x in reversed(dane) if teraz - x['t'] >= 60), None)
    p_2min = next((x['c'] for x in reversed(dane) if teraz - x['t'] >= 120), None)
    
    if not p_1min or not p_2min: return 0.1
    
    v1 = ((p_teraz - p_1min) / p_1min) * 100 
    v2 = ((p_1min - p_2min) / p_2min) * 100 
    
    return v1 - v2 

# ==============================================================================
# 🚀 GŁÓWNA PĘTLA PROGRAMU
# ==============================================================================
def main():
    cooldowny = {} 
    ostatni_skan_rynku = 0
    historia_cen = {} 
    
    print("=" * 65)
    print(f"🚀 SKANER V10.3 (FIX: CENA 0.00001 + BLACKLIST) START | OCHRONA: {INTERVAL_OCHRONY}s")
    print("=" * 65)

    while True:
        konfig = pobierz_konfiguracje()
        teraz_ts = time.time()
        teraz_str = datetime.now().strftime("%H:%M:%S")
        
        dane = get_binance_prices()
        if not dane:
            time.sleep(5)
            continue

        # Aktualizacja fizyki dla coinów, które spełniają warunki
        for sym, dt in dane.items():
            try:
                # [FIX] Tutaj też filtrujemy cenę, żeby nie zaśmiecać pamięci BTTC
                if float(dt['quoteVolume']) > MIN_VOL_24H and float(dt['lastPrice']) > MIN_CENA:
                    oblicz_przyspieszenie(sym, float(dt['lastPrice']))
            except: pass

        cooldowny = {k: v for k, v in cooldowny.items() if v > teraz_ts}
        
        # --- SEKCJA A: OCHRONA POZYCJI ---
        moje = pobierz_pozycje_skanera_z_bazy()
        
        for sym, info in moje.items():
            if sym in cooldowny: continue
            if sym not in dane: continue

            act = float(dane[sym]['lastPrice'])
            cena_wejscia = info['cena_wejscia']
            zm = ((act - cena_wejscia) / cena_wejscia) * 100
            
            max_z = info.get('max_zysk', 0.0)
            if zm > max_z:
                max_z = zm
                db.aktualizuj_max_zysk(info['unikalne_id'], max_z)
            
            czas_trwania = int((teraz_ts - info.get('czas_zakupu', teraz_ts)) / 60)
            akcja = None
            powod = ""
            
            # --- ZMIANA: CIASNY TRAILING STOP (0.8 zamiast 0.6) ---
            if zm < -1.8: akcja, powod = "STOP LOSS", f"Strata {zm:.2f}%"
            elif zm >= 25.0: akcja, powod = "MOONSHOT", f"Zysk {zm:.2f}%"
            elif max_z >= 1.2 and zm < 0.1: akcja, powod = "BREAK EVEN", "Ochrona kapitału"
            # Tu jest zmiana: oddajemy tylko 20% zysku
            elif max_z >= 2.5 and zm < (max_z * 0.8): akcja, powod = "TRAILING", f"Ochrona (Max: {max_z:.1f}%)"
            elif czas_trwania >= 4 and zm < 0.2: akcja, powod = "STAGNATION", "Brak ruchu (4min)"
            elif czas_trwania >= 60: akcja, powod = "TIMEOUT", "Koniec czasu (1h)"

            if akcja:
                zysk = pm.zwroc_srodki(sym, act, zrodlo="SKANER")
                kol = "🟢" if zysk > 0 else "🔴"
                print(f"⚡ {teraz_str} | {sym} | {akcja} ({powod}) | Wynik: {kol} {zysk:.2f} USDT | Max: {max_z:.2f}%")
                cooldowny[sym] = teraz_ts + COOLDOWN_CZAS

        # --- SEKCJA B: SKANOWANIE RYNKU ---
        if teraz_ts - ostatni_skan_rynku >= INTERVAL_SKANOWANIA_NOWYCH:
            moje = pobierz_pozycje_skanera_z_bazy()
            moje_aktywne = {k: v for k, v in moje.items() if k not in cooldowny}
            
            moje_cnt = len(moje_aktywne)
            wolne = MAX_POZYCJI_SKANERA - moje_cnt
            
            total = pm.oblicz_wartosc_total()            
            zysk_tot = total - 1000.00
            kol = "🟢" if zysk_tot >= 0 else "🔴"

            print(f"\n⏰ {teraz_str} | 🔄 SKAN: {konfig['NAZWA']} | Total: {total:.2f}$ ({kol}{zysk_tot:+.2f}) | Sloty: {moje_cnt}/{MAX_POZYCJI_SKANERA}")
            
            if moje_aktywne:
                print(f"   💼 TWOJE POZYCJE:")
                for sym, info in moje_aktywne.items():
                    if sym in dane:
                        act = float(dane[sym]['lastPrice'])
                        cena_wejscia = info['cena_wejscia']
                        zm = ((act - cena_wejscia) / cena_wejscia) * 100
                        czas = int((teraz_ts - info.get('czas_zakupu', teraz_ts)) / 60)
                        kol_poz = "🟢" if zm > 0 else "🔴"
                        print(f"      👉 {sym:<10} | {kol_poz} {zm:+.2f}% | Czas: {czas} min")

            wszystkie_ruchy = []
            for sym, dt in dane.items():
                try:
                    c = float(dt['lastPrice'])
                    v = float(dt['quoteVolume'])
                    
                    # [FIX] FILTR CENY - Tutaj odrzucamy śmieci jak BTTC
                    if v < MIN_VOL_24H or c < MIN_CENA: continue
                    
                    prev = historia_cen.get(sym, c)
                    zm = ((c - prev) / prev) * 100
                    historia_cen[sym] = c 
                    if zm > 0.5: wszystkie_ruchy.append({'s': sym, 'z': zm, 'c': c, 'v': v})
                except: continue
            
            wszystkie_ruchy.sort(key=lambda x: x['z'], reverse=True)
            
            if wszystkie_ruchy:
                print(f"   🔍 ANALIZA RYNKU (Top 3 skoki):")
                for t in wszystkie_ruchy[:3]:
                    acc = oblicz_przyspieszenie(t['s'], t['c'])
                    print(f"      👉 {t['s']}: +{t['z']:.2f}% (Accel: {acc:.2f})")
            else:
                print("   💤 Rynek śpi (brak nagłych ruchów > 0.5%)")

            if wolne > 0:
                kandydaci = []
                for k in wszystkie_ruchy:
                    if k['s'] in cooldowny or k['s'] in moje: continue
                    
                    if k['z'] >= konfig['PRÓG']:
                        
                        acc = oblicz_przyspieszenie(k['s'], k['c'])
                        if acc < PROG_ACCEL: continue
                            
                        # Sprawdzamy Blacklistę (FIXED: Uwzględnia NULL)
                        if czy_na_czarnej_liscie(k['s']):
                            # print(f"   ⛔ {k['s']} jest na Czarnej Liście")
                            continue

                        rsi = get_kline_rsi(k['s'])
                        if rsi < konfig['RSI']:
                            kandydaci.append({**k, 'r': rsi, 'acc': acc})
                
                if kandydaci:
                    print("-" * 65)
                    for k in kandydaci[:wolne]:
                        sukces, il, koszt = pm.pobierz_srodki(k['s'], k['c'], 0.10, "SKANER", "skalp")
                        if sukces:
                            v_mln = k['v'] / 1000000
                            print(f"🚀 {k['s']:<10} | +{k['z']:.2f}% 🔥 | Acc: {k['acc']:.2f} | RSI {k['r']:.0f} | KUPUJĘ")
                        else:
                            print(f"⚠️ {k['s']} | BRAK ŚRODKÓW")
                else:
                    print(f"   ⛔ Brak okazji (Wymogi: Wzrost > {konfig['PRÓG']}%, Accel > 0, Czysta Kartoteka).")
            else:
                print("⛔ Limit pozycji skanera osiągnięty. Czekam na sprzedaż.")

            print(f"\n💤 Czekam 5 minut na kolejny skan...")
            ostatni_skan_rynku = teraz_ts

        time.sleep(INTERVAL_OCHRONY)

if __name__ == "__main__":
    main()