import requests
import time
import sys
import os
from datetime import datetime, timedelta

# ==============================================================================
# 🚀 SKANER HYBRYDOWY V10.0 (SQL + FIZYKA + BLACKLIST)
# ==============================================================================

# --- 1. INTEGRACJA Z BAZĄ DANYCH ---
current_dir = os.path.dirname(os.path.abspath(__file__)) 
parent_dir = os.path.dirname(current_dir)              
sys.path.append(parent_dir)
os.chdir(parent_dir) # Kluczowe dla widoczności bazy

try:
    import portfel_manager as pm
    from database_handler import DatabaseHandler
except ImportError:
    print("❌ BŁĄD KRYTYCZNY: Brak modułów bazy/portfela w folderze nadrzędnym!")
    sys.exit()

db = DatabaseHandler()

# --- 2. KONFIGURACJA STRATEGII (TWOJA ORYGINALNA) ---
MIN_VOL_24H = 450000 
MAX_POZYCJI_SKANERA = 7 
INTERVAL_SKANOWANIA_NOWYCH = 300 # 5 minut
INTERVAL_OCHRONY = 10            # 10 sekund
COOLDOWN_CZAS = 3600      

CFG_AGRESYWNY = { "PRÓG": 2.2, "RSI": 88, "NAZWA": "🔥 AGRESYWNY (Pon-Sob)" }
CFG_BEZPIECZNY = { "PRÓG": 2.8, "RSI": 75, "NAZWA": "🛡️ BEZPIECZNY (Niedziela)" }

# --- [NOWOŚĆ] KONFIGURACJA OCHRONNA ---
BAN_DNI = 3  # Ile dni bana za stratę
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
    """Pobiera pozycje zrodlo='SKANER' z tabeli aktywne_pozycje"""
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

# --- [NOWOŚĆ] CZARNA LISTA SQL ---
def czy_na_czarnej_liscie(symbol):
    """Sprawdza, czy coin przyniósł stratę w ostatnich 3 dniach"""
    try:
        data_graniczna = (datetime.now() - timedelta(days=BAN_DNI)).timestamp()
        query = "SELECT count(*) FROM historia_transakcji WHERE symbol = ? AND zysk_proc < 0 AND czas_wyjscia > ?"
        db.cursor.execute(query, (symbol, data_graniczna))
        if db.cursor.fetchone()[0] > 0:
            return True
        return False
    except: return False

# --- [NOWOŚĆ] FIZYKA (PRZYSPIESZENIE) ---
def oblicz_przyspieszenie(symbol, current_price):
    """
    Zwraca acceleration (różnicę prędkości).
    Jeśli > 0 -> Przyspiesza.
    Jeśli < 0 -> Hamuje (nawet jak rośnie).
    """
    teraz = time.time()
    if symbol not in historia_cen_local:
        historia_cen_local[symbol] = []
    
    # Dodaj nową próbkę
    historia_cen_local[symbol].append({"c": current_price, "t": teraz})
    # Trzymaj tylko ostatnie 4 minuty
    historia_cen_local[symbol] = [x for x in historia_cen_local[symbol] if teraz - x['t'] < 240]
    
    dane = historia_cen_local[symbol]
    if len(dane) < 3: return 0.1 # Domyślnie lekki plus, żeby nie blokować na starcie
    
    # Szukamy ceny sprzed ~1 min i ~2 min
    p_teraz = dane[-1]['c']
    p_1min = next((x['c'] for x in reversed(dane) if teraz - x['t'] >= 60), None)
    p_2min = next((x['c'] for x in reversed(dane) if teraz - x['t'] >= 120), None)
    
    if not p_1min or not p_2min: return 0.1
    
    v1 = ((p_teraz - p_1min) / p_1min) * 100 # Prędkość teraz
    v2 = ((p_1min - p_2min) / p_2min) * 100 # Prędkość minutę temu
    
    return v1 - v2 # Przyspieszenie

# ==============================================================================
# 🚀 GŁÓWNA PĘTLA PROGRAMU
# ==============================================================================
def main():
    cooldowny = {} 
    ostatni_skan_rynku = 0
    historia_cen = {} 
    
    print("=" * 65)
    print(f"🚀 SKANER V10.0 (SQL+FIZYKA) START | OCHRONA: {INTERVAL_OCHRONY}s")
    print("=" * 65)

    while True:
        konfig = pobierz_konfiguracje()
        teraz_ts = time.time()
        teraz_str = datetime.now().strftime("%H:%M:%S")
        
        # 1. Sprawdzanie cen
        dane = get_binance_prices()
        if not dane:
            time.sleep(5)
            continue

        # --- [NOWOŚĆ] AKTUALIZACJA DANYCH FIZYCZNYCH (W TLE) ---
        # Robimy to dla wszystkich coinów z wolumenem, żeby mieć historię
        for sym, dt in dane.items():
            try:
                if float(dt['quoteVolume']) > MIN_VOL_24H:
                    oblicz_przyspieszenie(sym, float(dt['lastPrice']))
            except: pass
        # -------------------------------------------------------

        cooldowny = {k: v for k, v in cooldowny.items() if v > teraz_ts}
        
        # --- SEKCJA A: OCHRONA POZYCJI (Z SQL) ---
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
            
            # STRATEGIE WYJŚCIA (TWOJE)
            if zm < -1.8: akcja, powod = "STOP LOSS", f"Strata {zm:.2f}%"
            elif zm >= 25.0: akcja, powod = "MOONSHOT", f"Zysk {zm:.2f}%"
            elif max_z >= 1.2 and zm < 0.1: akcja, powod = "BREAK EVEN", "Ochrona kapitału"
            elif max_z >= 2.5 and zm < (max_z * 0.6): akcja, powod = "TRAILING", f"Ochrona (Max: {max_z:.1f}%)"
            elif czas_trwania >= 4 and zm < 0.2: akcja, powod = "STAGNATION", "Brak ruchu (4min)"
            elif czas_trwania >= 60: akcja, powod = "TIMEOUT", "Koniec czasu (1h)"

            if akcja:
                zysk = pm.zwroc_srodki(sym, act, zrodlo="SKANER")
                kol = "🟢" if zysk > 0 else "🔴"
                print(f"⚡ {teraz_str} | {sym} | {akcja} ({powod}) | Wynik: {kol} {zysk:.2f} USDT | Max: {max_z:.2f}%")
                cooldowny[sym] = teraz_ts + COOLDOWN_CZAS

        # --- SEKCJA B: SKANOWANIE RYNKU (Co 5 minut) ---
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

            # Analiza rynku
            wszystkie_ruchy = []
            for sym, dt in dane.items():
                try:
                    c = float(dt['lastPrice'])
                    v = float(dt['quoteVolume'])
                    if v < MIN_VOL_24H: continue
                    prev = historia_cen.get(sym, c)
                    zm = ((c - prev) / prev) * 100
                    historia_cen[sym] = c 
                    if zm > 0.5: wszystkie_ruchy.append({'s': sym, 'z': zm, 'c': c, 'v': v})
                except: continue
            
            wszystkie_ruchy.sort(key=lambda x: x['z'], reverse=True)
            
            if wszystkie_ruchy:
                print(f"   🔍 ANALIZA RYNKU (Top 3 skoki):")
                for t in wszystkie_ruchy[:3]:
                    # Obliczamy pęd tylko dla wyświetlenia
                    acc = oblicz_przyspieszenie(t['s'], t['c'])
                    print(f"      👉 {t['s']}: +{t['z']:.2f}% (Accel: {acc:.2f})")
            else:
                print("   💤 Rynek śpi (brak nagłych ruchów > 0.5%)")

            if wolne > 0:
                kandydaci = []
                for k in wszystkie_ruchy:
                    if k['s'] in cooldowny or k['s'] in moje: continue
                    
                    # 1. WARUNEK PODSTAWOWY: Wzrost > PRÓG (Prędkość)
                    if k['z'] >= konfig['PRÓG']:
                        
                        # 2. [NOWOŚĆ] WARUNEK FIZYKI: Przyspieszenie > 0 (Nie hamuje)
                        acc = oblicz_przyspieszenie(k['s'], k['c'])
                        if acc < PROG_ACCEL:
                            # print(f"   ⚠️ Odrzucam {k['s']} (Hamuje: {acc:.2f})") # Opcjonalny debug
                            continue
                            
                        # 3. [NOWOŚĆ] CZARNA LISTA SQL (3 dni bana)
                        if czy_na_czarnej_liscie(k['s']):
                            # print(f"   ⛔ Odrzucam {k['s']} (Czarna Lista)")
                            continue

                        # 4. RSI (Stary dobry filtr)
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