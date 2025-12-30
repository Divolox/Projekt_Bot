import requests
import time
import sys
import os
from datetime import datetime

# ==========================================
# 🚀 SKANER HYBRYDOWY V7.7 (FIXED + DIAGNOSTYKA)
# ==========================================

# --- INTEGRACJA Z PORTFELEM ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

try:
    import portfel_manager as pm
except ImportError:
    print("❌ BŁĄD: Brak 'portfel_manager.py' w folderze głównym!")
    sys.exit()

# KONFIGURACJA
MIN_VOL_24H = 450000
MAX_POZYCJI_SKANERA = 7 
INTERVAL_SKANOWANIA = 600 # 10 minut
COOLDOWN_CZAS = 2700

# STRATEGIA (Próg 2.0% - Agresywny)
CFG_AGRESYWNY = { "PRÓG": 2.0, "RSI": 92, "NAZWA": "🔥 AGRESYWNY (Pon-Sob)" }
CFG_BEZPIECZNY = { "PRÓG": 2.8, "RSI": 78, "NAZWA": "🛡️ BEZPIECZNY (Niedziela)" }

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
        resp = requests.get(url, timeout=10).json()
        closes = [float(x[4]) for x in resp]
        deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]
        if not gains: return 0
        if not losses: return 100
        rs = (sum(gains)/len(gains)) / (sum(losses)/len(losses))
        return 100 - (100 / (1 + rs))
    except: return 50

def main():
    cooldowny = {} 
    ostatni_skan_rynku = 0
    historia_cen = {}
    
    # Inicjalizacja portfela
    pm.wczytaj_portfel()
    
    print("=" * 65)
    print(f"🚀 SKANER V7.7 (FIXED) START | LIMIT: {MAX_POZYCJI_SKANERA}")
    print(f"📂 Bank: {pm.PLIK_PORTFELA}")
    print("=" * 65)

    while True:
        konfig = pobierz_konfiguracje()
        teraz_ts = time.time()
        teraz_str = datetime.now().strftime("%H:%M:%S")
        
        dane = get_binance_prices()
        if not dane:
            print(f"⚠️ {teraz_str} Błąd pobierania cen...")
            time.sleep(10)
            continue

        cooldowny = {k: v for k, v in cooldowny.items() if v > teraz_ts}
        portfel = pm.wczytaj_portfel()
        
        # 1. OBSŁUGA POZYCJI
        moje = {k: v for k, v in portfel.get("pozycje", {}).items() if v.get('zrodlo') == 'SKANER'}
        
        for sym, info in moje.items():
            if sym in dane:
                act = float(dane[sym]['lastPrice'])
                zm = ((act - info['cena_wejscia']) / info['cena_wejscia']) * 100
                
                max_z = info.get('max_zysk', 0.0)
                if zm > max_z:
                    max_z = zm
                    portfel["pozycje"][sym]['max_zysk'] = max_z
                    pm.zapisz_portfel(portfel)
                
                czas = int((teraz_ts - info.get('timestamp_wejscia', teraz_ts)) / 60)
                akcja = None
                powod = ""
                
                # Strategia Wyjścia
                if zm < -4.5: akcja, powod = "STOP LOSS", f"Strata {zm:.2f}%"
                elif zm >= 20.0: akcja, powod = "MOONSHOT", f"Zysk {zm:.2f}%"
                elif max_z >= 10.0 and zm < (max_z - 2.0): akcja, powod = "SNIPER", "Zjazd"
                elif max_z >= 1.5 and zm < (max_z * 0.6): akcja, powod = "TRAILING", "Ochrona"
                elif czas >= 10 and czas <= 12 and zm < -1.5: akcja, powod = "INSTANT DEATH", "Słaby start"
                elif czas >= 20 and zm < 0.2: akcja, powod = "FAST DEATH", "Muł"
                elif czas >= 60: akcja, powod = "KONIEC", "Czas"

                if akcja:
                    zysk = pm.zwroc_srodki(sym, act)
                    kol = "🟢" if zysk > 0 else "🔴"
                    print(f"{teraz_str} | {sym} | {akcja} ({powod}) | Wynik: {kol} {zysk:.2f} USDT")
                    cooldowny[sym] = teraz_ts + COOLDOWN_CZAS

        # 2. SKANOWANIE
        if teraz_ts - ostatni_skan_rynku >= INTERVAL_SKANOWANIA:
            portfel = pm.wczytaj_portfel()
            moje_cnt = len([p for p in portfel.get("pozycje", {}).values() if p.get('zrodlo') == 'SKANER'])
            wolne = MAX_POZYCJI_SKANERA - moje_cnt
            
            total = pm.oblicz_wartosc_total()
            zysk_tot = total - 1000.00
            kol = "🟢" if zysk_tot >= 0 else "🔴"

            print(f"\n🔄 SKAN: {konfig['NAZWA']} | Saldo: {total:.2f}$ ({kol}{zysk_tot:+.2f}) | Sloty: {moje_cnt}/{MAX_POZYCJI_SKANERA}")
            
            # DIAGNOSTYKA PULSU RYNKU (To Ci pokaże co się dzieje)
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
            
            print("\n🔍 ANALIZA RYNKU...")
            if wszystkie_ruchy:
                print(f"   👀 PULS (Top 3 ruchy):")
                for t in wszystkie_ruchy[:3]:
                    print(f"      👉 {t['s']}: +{t['z']:.2f}%")
            else:
                print("   👀 Rynek stoi (brak ruchów > 0.5%)")

            # KUPOWANIE
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
                            print(f"🚀 {k['s']:<10} | +{k['z']:.2f}% 🔥 | {v_mln:.2f}M      | RSI {k['r']:.0f} | KUPUJĘ")
                            print(f"   📉 POBIERAM Z PORTFELA: -{koszt:.2f} USDT")
                        else:
                            print(f"⚠️ {k['s']} | BRAK ŚRODKÓW")
                else:
                    print(f"   ⛔ Brak kandydatów spełniających warunki (Próg > {konfig['PRÓG']}%, RSI < {konfig['RSI']}).")
            else:
                print("⛔ Limit pozycji osiągnięty.")

            print(f"\n💤 Czekam 10 minut...")
            ostatni_skan_rynku = teraz_ts

        time.sleep(60 - time.time() % 60)

if __name__ == "__main__":
    main()