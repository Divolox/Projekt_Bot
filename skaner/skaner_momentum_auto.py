import requests
import time
import sys
import os
from datetime import datetime

# ==========================================
# 🚀 SKANER HYBRYDOWY V7.5 (FINAL LOGS)
# ==========================================
# 1. Jasne logi finansowe (ile pobrał, ile oddał).
# 2. Limit MAX 7 pozycji (sztywny).
# 3. Pełna integracja z portfel_manager.py
# ==========================================

# --- PODŁĄCZENIE DO PORTFEL MANAGER (Folder Wyżej) ---
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)

try:
    import portfel_manager as pm
except ImportError:
    print("❌ BŁĄD KRYTYCZNY: Nie znaleziono 'portfel_manager.py' w folderze głównym!")
    sys.exit()

# KONFIGURACJA
MIN_VOL_24H = 450000
MAX_POZYCJI_SKANERA = 7  # <--- TU JEST TWOJE OGRANICZENIE
INTERVAL_SKANOWANIA = 600
COOLDOWN_CZAS = 2700

# USTAWIENIA DYNAMICZNE
CFG_AGRESYWNY = { "PRÓG": 2.0, "RSI": 92, "NAZWA": "🔥 AGRESYWNY (Pon-Sob)" }
CFG_BEZPIECZNY = { "PRÓG": 2.8, "RSI": 78, "NAZWA": "🛡️ BEZPIECZNY (Niedziela)" }

def pobierz_konfiguracje():
    return CFG_BEZPIECZNY if datetime.today().weekday() == 6 else CFG_AGRESYWNY

def get_binance_prices():
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        resp = requests.get(url, timeout=15).json()
        return {x['symbol']: x for x in resp if x['symbol'].endswith('USDT')}
    except Exception: return {}

def get_kline_rsi(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit=20"
        resp = requests.get(url, timeout=10).json()
        if not resp: return 50
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
    historia_cen = {}
    cooldowny = {} 
    ostatni_skan_rynku = 0
    
    # Inicjalizacja portfela
    pm.wczytaj_portfel()
    
    print("=" * 65)
    print(f"🚀 SKANER V7.5 START | LIMIT: {MAX_POZYCJI_SKANERA} POZYCJI")
    print(f"📂 Bank: {pm.PLIK_PORTFELA}")
    print("=" * 65)

    while True:
        konfig = pobierz_konfiguracje()
        teraz_ts = time.time()
        teraz_str = datetime.now().strftime("%H:%M:%S")
        
        dane = get_binance_prices()
        if not dane:
            print(f"⚠️ {teraz_str} Błąd pobierania cen. Czekam...")
            time.sleep(10)
            continue

        cooldowny = {k: v for k, v in cooldowny.items() if v > teraz_ts}
        portfel = pm.wczytaj_portfel()
        
        # 1. OBSŁUGA POZYCJI
        do_usuniecia = []
        moje_pozycje = {k: v for k, v in portfel["pozycje"].items() if v.get('zrodlo') == 'SKANER'}

        for sym, info in moje_pozycje.items():
            if sym in dane:
                cena_akt = float(dane[sym]['lastPrice'])
                cena_wej = info['cena_wejscia']
                zmiana = ((cena_akt - cena_wej) / cena_wej) * 100
                
                # Aktualizacja Max Zysku
                max_zysk = info.get('max_zysk', 0.0)
                if zmiana > max_zysk:
                    max_zysk = zmiana
                    portfel["pozycje"][sym]['max_zysk'] = max_zysk
                    pm.zapisz_portfel(portfel)
                
                czas_trwania = int((teraz_ts - info.get('timestamp_wejscia', teraz_ts)) / 60)
                
                # STRATEGIA WYJŚCIA
                action = None
                ikona_akcji = "❓"
                powod = ""

                if zmiana < -4.5: 
                        action = "STOP LOSS"
                        ikona_akcji = "💀"
                        powod = f"Strata: {zmiana:.2f}%"
                elif zmiana >= 20.0: 
                        action = "MOONSHOT"
                        ikona_akcji = "🚀"
                        powod = f"Zysk: {zmiana:.2f}%"
                elif max_zysk >= 10.0 and zmiana < (max_zysk - 2.0):
                    action = "SNIPER EXIT"
                    ikona_akcji = "💰"
                    powod = f"Zjazd z {max_zysk:.2f}%"
                elif max_zysk >= 1.5 and max_zysk < 10.0 and zmiana < (max_zysk * 0.6):
                    action = "SMART TRAILING"
                    ikona_akcji = "🛡️"
                    powod = f"Zjazd z {max_zysk:.2f}%"
                elif czas_trwania >= 9 and czas_trwania <= 11 and zmiana < -1.5:
                    action = "INSTANT DEATH"
                    ikona_akcji = "🗑️"
                    powod = f"Słaby start"
                elif czas_trwania >= 19 and zmiana < 0.2:
                    action = "FAST DEATH"
                    ikona_akcji = "🗑️"
                    powod = f"Muł"
                elif czas_trwania >= 60:
                    action = "KONIEC TESTU"
                    ikona_akcji = "🏁"
                    powod = "Czas minął"

                if action:
                    # REALIZACJA ZYSKU/STRATY
                    zysk_usdt = pm.zwroc_srodki(sym, cena_akt)
                    ikona_wyniku = "🟢" if zysk_usdt > 0 else "🔴"
                    
                    # LOGOWANIE ZE SZCZEGÓŁAMI (PROCENT + KWOTA)
                    print(f"{ikona_akcji} {teraz_str} | {sym:<6} | {action}: {powod}")
                    print(f"   💵 WYNIK: {ikona_wyniku} {zmiana:+.2f}% ({zysk_usdt:+.2f} USDT) | Kasa wraca do portfela")
                    
                    do_usuniecia.append(sym)
                    cooldowny[sym] = teraz_ts + COOLDOWN_CZAS
        
        # 2. SKANOWANIE RYNKU
        if teraz_ts - ostatni_skan_rynku >= INTERVAL_SKANOWANIA:
            portfel = pm.wczytaj_portfel()
            
            # --- WERYFIKACJA LIMITU 7 POZYCJI ---
            moje_pozycje_aktualne = len([p for p in portfel["pozycje"].values() if p.get('zrodlo') == 'SKANER'])
            wolne_sloty = MAX_POZYCJI_SKANERA - moje_pozycje_aktualne
            
            wartosc_total = pm.oblicz_wartosc_total() # (Gotówka + Aktywa)
            zysk_total = wartosc_total - 1000.00
            kolor_salda = "🟢" if zysk_total >= 0 else "🔴"

            print(f"\n🔄 SKANOWANIE: {teraz_str} | Tryb: {konfig['NAZWA']}")
            print("=" * 65)
            print(f"💰 SALDO CAŁKOWITE: {wartosc_total:.2f} USDT ({kolor_salda}{zysk_total:+.2f})")
            print(f"💵 WOLNA GOTÓWKA:   {portfel['saldo_gotowka']:.2f} USDT")
            print(f"📊 SLOTY SKANERA:   {moje_pozycje_aktualne} zajęte / {MAX_POZYCJI_SKANERA} max")
            print("-" * 65)
            
            print(f"{'SYMBOL':<10} | {'MOMENTUM':<12} | {'VOL (24h)':<10} | {'RSI':<6} | {'STATUS':<15}")
            print("-" * 65)
            
            # Raport pozycji
            if portfel["pozycje"]:
                for sym, info in portfel["pozycje"].items():
                    if sym in dane:
                        cena_akt = float(dane[sym]['lastPrice'])
                        zmiana = ((cena_akt - info['cena_wejscia']) / info['cena_wejscia']) * 100
                        # Szacowany wynik USDT w locie
                        wartosc_teraz = (info['ilosc_coinow'] * cena_akt) * (1 - 0.00075)
                        pnl = wartosc_teraz - info['wartosc_wejscia']
                        ikona = "🟢" if pnl > 0 else "🔴"
                        zrodlo = info.get('zrodlo', '?')
                        print(f"   🕒 {sym:<6} ({zrodlo}) | {ikona} {zmiana:+.2f}% ({pnl:+.2f} USDT) | {int((teraz_ts - info['timestamp_wejscia'])/60)}m")
            else:
                print("   (Brak otwartych pozycji)")

            print("\n🔍 ANALIZA RYNKU (Szukam kandydatów)...")
            
            if wolne_sloty > 0:
                kandydaci_w_cyklu = []
                for sym, data in dane.items():
                    try:
                        if sym in cooldowny or sym in portfel["pozycje"]: continue
                        c = float(data['lastPrice'])
                        v = float(data['quoteVolume'])
                        if v < MIN_VOL_24H: continue
                        
                        prev = historia_cen.get(sym, c)
                        zm = ((c - prev) / prev) * 100
                        historia_cen[sym] = c 
                        
                        if zm >= konfig['PRÓG']:
                            rsi = get_kline_rsi(sym)
                            if rsi < konfig['RSI']:
                                kandydaci_w_cyklu.append({'symbol': sym, 'zmiana': zmiana, 'vol': vol, 'rsi': rsi, 'cena': cena})
                    except: continue

                if kandydaci_w_cyklu:
                    kandydaci_w_cyklu.sort(key=lambda x: x['zmiana'], reverse=True)
                    najlepsi = kandydaci_w_cyklu[:wolne_sloty]
                    
                    for k in najlepsi:
                        sym = k['symbol']
                        vol_str = f"{k['vol']/1000000:.2f}M" if k['vol'] > 1000000 else f"{k['vol']/1000:.0f}k"
                        
                        # --- PRÓBA ZAKUPU (10% kapitału) ---
                        sukces, ilosc, koszt = pm.pobierz_srodki(sym, k['cena'], 0.10, "SKANER")
                        
                        if sukces:
                            print(f"🚀 {sym:<10} | {k['zmiana']:+.2f}% 🔥     | {vol_str:<10} | {k['rsi']:.0f}     | KUPUJĘ (TOP 10)!")
                            print(f"   📉 POBIERAM Z PORTFELA: -{koszt:.2f} USDT")
                        else:
                            print(f"⚠️ {sym:<10} | {k['zmiana']:+.2f}% 🔥     | {vol_str:<10} | {k['rsi']:.0f}     | BRAK ŚRODKÓW")
                else:
                    print("   (Cisza. Brak silnych ruchów...)")
            else:
                print("⛔ Limit pozycji Skanera osiągnięty (7/7). Czekam na zamknięcia.")
            
            print(f"\n💤 Czekam 10 minut...")
            ostatni_skan_rynku = teraz_ts

        # Czekanie do pełnej minuty
        teraz = datetime.now()
        seconds = 60 - teraz.second
        time.sleep(seconds if seconds > 0 else 1)

if __name__ == "__main__":
    main()

