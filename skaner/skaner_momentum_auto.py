import requests
import time
import sys
import os
from datetime import datetime

# ==============================================================================
# 🚀 SKANER HYBRYDOWY V9.0 (WERSJA SQLITE - PEŁNA LOGIKA)
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
        # Pobieramy to co potrzebujesz: symbol, cena_wejscia, czas_wejscia, max_zysk, unikalne_id
        db.cursor.execute("SELECT unikalne_id, symbol, cena_wejscia, czas_wejscia, max_zysk FROM aktywne_pozycje WHERE zrodlo='SKANER'")
        rows = db.cursor.fetchall()
        # Przerabiamy na format słownika, żeby Twoja logika pętli działała bez zmian
        pozycje_dict = {}
        for r in rows:
            uid, sym, cena, czas, max_z = r
            pozycje_dict[sym] = {
                'unikalne_id': uid,
                'symbol': sym,
                'cena_wejscia': cena,
                'czas_zakupu': czas, # Mapujemy czas_wejscia na czas_zakupu (dla zgodności z Twoim kodem)
                'max_zysk': max_z
            }
        return pozycje_dict
    except Exception as e:
        print(f"⚠️ Błąd SQL w Skanerze: {e}")
        return {}

# ==============================================================================
# 🚀 GŁÓWNA PĘTLA PROGRAMU
# ==============================================================================
def main():
    cooldowny = {} 
    ostatni_skan_rynku = 0
    historia_cen = {} 
    
    print("=" * 65)
    print(f"🚀 SKANER V9.0 (SQL) START | OCHRONA: {INTERVAL_OCHRONY}s | BAZA: baza_bota.db")
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

        cooldowny = {k: v for k, v in cooldowny.items() if v > teraz_ts}
        
        # --- SEKCJA A: OCHRONA POZYCJI (TERAZ Z SQL) ---
        moje = pobierz_pozycje_skanera_z_bazy()
        
        for sym, info in moje.items():
            if sym in cooldowny: continue
            if sym not in dane: continue

            act = float(dane[sym]['lastPrice'])
            cena_wejscia = info['cena_wejscia']
            zm = ((act - cena_wejscia) / cena_wejscia) * 100
            
            # Aktualizacja Max Zysku w bazie (zamiast w JSONie)
            max_z = info.get('max_zysk', 0.0)
            if zm > max_z:
                max_z = zm
                db.aktualizuj_max_zysk(info['unikalne_id'], max_z)
            
            czas_trwania = int((teraz_ts - info.get('czas_zakupu', teraz_ts)) / 60)
            akcja = None
            powod = ""
            
            # ==============================
            # ⚔️ STRATEGIE WYJŚCIA (TWOJE)
            # ==============================
            if zm < -1.8: akcja, powod = "STOP LOSS", f"Strata {zm:.2f}%"
            elif zm >= 25.0: akcja, powod = "MOONSHOT", f"Zysk {zm:.2f}%"
            elif max_z >= 1.2 and zm < 0.1: akcja, powod = "BREAK EVEN", "Ochrona kapitału"
            elif max_z >= 2.5 and zm < (max_z * 0.6): akcja, powod = "TRAILING", f"Ochrona (Max: {max_z:.1f}%)"
            elif czas_trwania >= 4 and zm < 0.2: akcja, powod = "STAGNATION", "Brak ruchu (4min)"
            elif czas_trwania >= 60: akcja, powod = "TIMEOUT", "Koniec czasu (1h)"

            if akcja:
                # Używamy PM do zwrotu (on obsłuży SQL, usunie pozycję i doda hajs)
                zysk = pm.zwroc_srodki(sym, act, zrodlo="SKANER")
                kol = "🟢" if zysk > 0 else "🔴"
                print(f"⚡ {teraz_str} | {sym} | {akcja} ({powod}) | Wynik: {kol} {zysk:.2f} USDT | Max: {max_z:.2f}%")
                cooldowny[sym] = teraz_ts + COOLDOWN_CZAS

        # --- SEKCJA B: SKANOWANIE RYNKU (Co 5 minut) ---
        if teraz_ts - ostatni_skan_rynku >= INTERVAL_SKANOWANIA_NOWYCH:
            # Ponowne pobranie stanu z bazy (mogło się coś zmienić)
            moje = pobierz_pozycje_skanera_z_bazy()
            # Filtrujemy cooldowny
            moje_aktywne = {k: v for k, v in moje.items() if k not in cooldowny}
            
            moje_cnt = len(moje_aktywne)
            wolne = MAX_POZYCJI_SKANERA - moje_cnt
            
            # Pobieramy total z managera (on sumuje saldo + wartość wszystkich pozycji z bazy)
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
                    print(f"      👉 {t['s']}: +{t['z']:.2f}%")
            else:
                print("   💤 Rynek śpi (brak nagłych ruchów > 0.5%)")

            if wolne > 0:
                kandydaci = []
                for k in wszystkie_ruchy:
                    # Sprawdzamy czy nie mamy tego coina (używając listy kluczy z bazy)
                    if k['s'] in cooldowny or k['s'] in moje: continue
                    if k['z'] >= konfig['PRÓG']:
                        rsi = get_kline_rsi(k['s'])
                        if rsi < konfig['RSI']:
                            kandydaci.append({**k, 'r': rsi})
                
                if kandydaci:
                    print("-" * 65)
                    for k in kandydaci[:wolne]:
                        # Zakup przez managera (SQL INSERT)
                        sukces, il, koszt = pm.pobierz_srodki(k['s'], k['c'], 0.10, "SKANER", "skalp")
                        if sukces:
                            v_mln = k['v'] / 1000000
                            print(f"🚀 {k['s']:<10} | +{k['z']:.2f}% 🔥 | Vol: {v_mln:.2f}M | RSI {k['r']:.0f} | KUPUJĘ")
                        else:
                            # Jeśli brak środków, to nic nie robimy
                            print(f"⚠️ {k['s']} | BRAK ŚRODKÓW")
                else:
                    print(f"   ⛔ Brak okazji (Wymogi: Wzrost > {konfig['PRÓG']}%, RSI < {konfig['RSI']}).")
            else:
                print("⛔ Limit pozycji skanera osiągnięty. Czekam na sprzedaż.")

            print(f"\n💤 Czekam 5 minut na kolejny skan...")
            ostatni_skan_rynku = teraz_ts

        time.sleep(INTERVAL_OCHRONY)

if __name__ == "__main__":
    main()