import requests
import time
import sys
import os
from datetime import datetime

# ==============================================================================
# 🚀 SKANER HYBRYDOWY V8.11 (FIX PODWÓJNEJ SPRZEDAŻY)
# ==============================================================================

# --- 1. INTEGRACJA Z PORTFELEM ---
current_dir = os.path.dirname(os.path.abspath(__file__)) 
parent_dir = os.path.dirname(current_dir)              
sys.path.append(parent_dir)

try:
    import portfel_manager as pm
    pm.PLIK_PORTFELA = os.path.join(parent_dir, "portfel.json")
    print(f"🔗 Połączono ze wspólnym portfelem: {pm.PLIK_PORTFELA}")
except ImportError:
    print("❌ BŁĄD KRYTYCZNY: Brak 'portfel_manager.py' w folderze głównym!")
    sys.exit()

# --- 2. KONFIGURACJA STRATEGII ---
MIN_VOL_24H = 450000 
MAX_POZYCJI_SKANERA = 7 
INTERVAL_SKANOWANIA_NOWYCH = 300 # 5 minut
INTERVAL_OCHRONY = 10            # 10 sekund
COOLDOWN_CZAS = 3600      

CFG_AGRESYWNY = { "PRÓG": 2.2, "RSI": 88, "NAZWA": "🔥 AGRESYWNY (Pon-Sob)" }
CFG_BEZPIECZNY = { "PRÓG": 3.5, "RSI": 75, "NAZWA": "🛡️ BEZPIECZNY (Niedziela)" }

def pobierz_konfiguracje():
    return CFG_BEZPIECZNY if datetime.today().weekday() == 6 else CFG_AGRESYWNY

def get_binance_prices():
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        resp = requests.get(url, timeout=15).json() # Timeout 15s dla stabilności
        return {x['symbol']: x for x in resp if x['symbol'].endswith('USDT')}
    except Exception as e:
        # Cichy błąd przy braku neta, żeby nie spamować
        return {}

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

# ==============================================================================
# 🚀 GŁÓWNA PĘTLA PROGRAMU
# ==============================================================================
def main():
    cooldowny = {} 
    ostatni_skan_rynku = 0
    historia_cen = {} 
    
    pm.wczytaj_portfel()
    
    print("=" * 65)
    print(f"🚀 SKANER V8.11 START | OCHRONA: {INTERVAL_OCHRONY}s | FIX: ANTI-ZOMBIE")
    print(f"📂 Portfel: {pm.PLIK_PORTFELA}")
    print("=" * 65)

    while True:
        konfig = pobierz_konfiguracje()
        teraz_ts = time.time()
        teraz_str = datetime.now().strftime("%H:%M:%S")
        
        # 1. Sprawdzanie cen (SZYBKA OCHRONA - co 10s)
        dane = get_binance_prices()
        if not dane:
            time.sleep(5)
            continue

        # Czyścimy stare cooldowny, ale zostawiamy te aktywne
        cooldowny = {k: v for k, v in cooldowny.items() if v > teraz_ts}
        portfel = pm.wczytaj_portfel() 
        
        # --- SEKCJA A: OCHRONA POZYCJI ---
        moje = {k: v for k, v in portfel.get("pozycje", {}).items() if v.get('zrodlo') == 'SKANER'}
        
        for sym, info in moje.items():
            # 🔥 FIX: Jeśli coin jest w cooldownie, to znaczy że przed chwilą go sprzedaliśmy!
            # Ignorujemy go tutaj, żeby nie sprzedać drugi raz zanim plik się odświeży.
            if sym in cooldowny:
                continue

            if sym in dane:
                act = float(dane[sym]['lastPrice'])
                cena_wejscia = info['cena_wejscia']
                zm = ((act - cena_wejscia) / cena_wejscia) * 100
                
                max_z = info.get('max_zysk', 0.0)
                if zm > max_z:
                    max_z = zm
                    portfel["pozycje"][sym]['max_zysk'] = max_z
                    pm.zapisz_portfel(portfel)
                
                czas_trwania = int((teraz_ts - info.get('timestamp_wejscia', teraz_ts)) / 60)
                akcja = None
                powod = ""
                
                # ==============================
                # ⚔️ STRATEGIE WYJŚCIA
                # ==============================
                
                # 1. STOP LOSS (Twardy)
                if zm < -3.5: 
                    akcja, powod = "STOP LOSS", f"Strata {zm:.2f}%"
                
                # 2. MOONSHOT (Wielka Pompa)
                elif zm >= 25.0: 
                    akcja, powod = "MOONSHOT", f"Zysk {zm:.2f}%"
                
                # 3. TRAILING STOP (Ochrona zysku)
                elif max_z >= 2.0 and zm < (max_z * 0.6): 
                    akcja, powod = "TRAILING", f"Ochrona (Max: {max_z:.1f}%)"
                
                # 4. STAGNATION KILLER
                elif czas_trwania >= 6 and zm < 0.3:
                    akcja, powod = "STAGNATION", "Brak ruchu (6min)"
                
                # 5. TIMEOUT (Ostateczność)
                elif czas_trwania >= 60: 
                    akcja, powod = "TIMEOUT", "Koniec czasu (1h)"

                if akcja:
                    zysk = pm.zwroc_srodki(sym, act)
                    kol = "🟢" if zysk > 0 else "🔴"
                    print(f"⚡ {teraz_str} | {sym} | {akcja} ({powod}) | Wynik: {kol} {zysk:.2f} USDT | Max: {max_z:.2f}%")
                    # Dodajemy do cooldownu NATYCHMIAST po wykryciu akcji
                    cooldowny[sym] = teraz_ts + COOLDOWN_CZAS

        # --- SEKCJA B: SKANOWANIE RYNKU (Co 5 minut) ---
        if teraz_ts - ostatni_skan_rynku >= INTERVAL_SKANOWANIA_NOWYCH:
            # Ponowne wczytanie portfela po operacjach
            portfel = pm.wczytaj_portfel()
            
            # Odświeżamy listę 'moje' (filtrując te w cooldownie żeby nie pokazywać duchów)
            moje_raw = {k: v for k, v in portfel.get("pozycje", {}).items() if v.get('zrodlo') == 'SKANER'}
            moje = {k: v for k, v in moje_raw.items() if k not in cooldowny}
            
            moje_cnt = len(moje)
            wolne = MAX_POZYCJI_SKANERA - moje_cnt
            
            total = pm.oblicz_wartosc_total()            
            gotowka = portfel.get("saldo_gotowka", 0)    
            zysk_tot = total - 1000.00
            kol = "🟢" if zysk_tot >= 0 else "🔴"

            print(f"\n⏰ {teraz_str} | 🔄 SKAN: {konfig['NAZWA']} | Total: {total:.2f}$ ({kol}{zysk_tot:+.2f}) | Sloty: {moje_cnt}/{MAX_POZYCJI_SKANERA}")
            
            if moje:
                print(f"   💼 TWOJE POZYCJE:")
                for sym, info in moje.items():
                    if sym in dane:
                        act = float(dane[sym]['lastPrice'])
                        cena_wejscia = info['cena_wejscia']
                        zm = ((act - cena_wejscia) / cena_wejscia) * 100
                        czas = int((teraz_ts - info.get('timestamp_wejscia', teraz_ts)) / 60)
                        kol_poz = "🟢" if zm > 0 else "🔴"
                        print(f"      👉 {sym:<10} | {kol_poz} {zm:+.2f}% | Czas: {czas} min")

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
                    if k['s'] in cooldowny or k['s'] in portfel.get("pozycje", {}): continue
                    if k['z'] >= konfig['PRÓG']:
                        rsi = get_kline_rsi(k['s'])
                        if rsi < konfig['RSI']:
                            kandydaci.append({**k, 'r': rsi})
                
                if kandydaci:
                    print("-" * 65)
                    for k in kandydaci[:wolne]:
                        sukces, il, koszt = pm.pobierz_srodki(k['s'], k['c'], 0.10, "SKANER")
                        if sukces:
                            v_mln = k['v'] / 1000000
                            print(f"🚀 {k['s']:<10} | +{k['z']:.2f}% 🔥 | Vol: {v_mln:.2f}M | RSI {k['r']:.0f} | KUPUJĘ")
                        else:
                            print(f"⚠️ {k['s']} | BRAK ŚRODKÓW ({gotowka:.2f}$)")
                else:
                    print(f"   ⛔ Brak okazji (Wymogi: Wzrost > {konfig['PRÓG']}%, RSI < {konfig['RSI']}).")
            else:
                print("⛔ Limit pozycji skanera osiągnięty. Czekam na sprzedaż.")

            print(f"\n💤 Czekam 5 minut na kolejny skan...")
            ostatni_skan_rynku = teraz_ts

        time.sleep(INTERVAL_OCHRONY)

if __name__ == "__main__":
    main()