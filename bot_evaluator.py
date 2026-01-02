import json
import time
import os
import datetime
import portfel_manager as pm

# ==========================================
# ⚙️ KONFIGURACJA
# ==========================================
PLIK_STRATEGII = "strategie_bota.json"
PLIK_RYNKU = "rynek.json"

# --- ZASADY WYJŚCIA (GLOBALNE) ---
HARD_STOP_LOSS = -2.5         
HARD_TAKE_PROFIT = 25.0       
TRAILING_START_MIN = 1.5      
TRAILING_DROP_SMALL = 0.5     
TRAILING_START_BIG = 5.0      
TRAILING_DROP_BIG = 1.5       

def wczytaj_json(plik):
    if not os.path.exists(plik): return {}
    try:
        with open(plik, "r") as f: return json.load(f)
    except: return {}

def zapisz_json(plik, dane):
    try:
        with open(plik, "w") as f: json.dump(dane, f, indent=4)
    except: pass

# =========================================================
# 🧠 MÓZG SZCZEGÓŁOWY (3 ŚWIATY + WOLUMEN + RSI)
# To jest Twoja funkcja z "3 Światami" (bez Trailingu/Czasu)
# =========================================================
def ocen_pozycje(pozycja, aktualna_cena, aktualne_rsi, vol_ratio):
    symbol = pozycja.get('symbol')
    typ = str(pozycja.get('typ', 'STANDARD')).lower()
    
    c_start = float(pozycja.get('cena_wejscia') or pozycja.get('cena_start') or 0)
    if c_start == 0: return False, ""

    wynik_proc = ((aktualna_cena - c_start) / c_start) * 100
    
    # 🌍 1. TYGODNIOWA (Inwestor)
    if "tyg" in typ:
        if wynik_proc <= -12.0: return True, f"🛑 HARD SL 1W ({wynik_proc:.2f}%)"
        if wynik_proc < -5.0 and vol_ratio > 2.0: return True, f"📉 PANIC SELL 1W (Krach Vol)"
        if wynik_proc > 15.0 and aktualne_rsi > 80: return True, f"💰 SMART TP 1W (RSI {aktualne_rsi:.0f})"
        if wynik_proc >= 30.0: return True, f"🚀 MOON TP 1W ({wynik_proc:.2f}%)"
        return False, "TRZYMAM"

    # 🌍 2. GODZINOWA (Skalper)
    elif "godz" in typ:
        if wynik_proc <= -2.5: return True, f"🛑 HARD SL 1H ({wynik_proc:.2f}%)"
        if wynik_proc < -1.0 and vol_ratio > 1.5: return True, f"📉 VOLUME DUMP 1H"
        if wynik_proc < -1.2 and aktualne_rsi > 45: return True, f"📉 SMART CUT 1H (Słabe RSI)"
        if wynik_proc > 1.5 and vol_ratio < 0.6: return True, f"💰 FAKE PUMP TP (Brak Vol)"
        if wynik_proc > 1.5 and aktualne_rsi > 72: return True, f"💰 RSI TP 1H"
        return False, "TRZYMAM"

    # 🌍 3. SWING (4H / 1D)
    else:
        limit_sl = -4.0 if "4h" in typ else -8.0
        if wynik_proc <= limit_sl: return True, f"🛑 HARD SL ({wynik_proc:.2f}%)"
        if wynik_proc < -2.0 and vol_ratio > 1.8: return True, f"📉 VOLUME DUMP"
        if wynik_proc < -2.0 and aktualne_rsi > 42: return True, f"📉 SMART CUT"
        if wynik_proc > 4.0 and aktualne_rsi > 75: return True, f"💰 SMART TP"
        if wynik_proc >= 10.0: return True, f"🚀 HARD TP ({wynik_proc:.2f}%)"
        return False, "TRZYMAM"

# =========================================================
# 🔧 SILNIK GŁÓWNY (PĘTLA Z PEŁNĄ LOGIKĄ)
# =========================================================
def main():
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 🛡️ EVALUATOR: Weryfikacja (Original Full)...")

    raw_strategies = wczytaj_json(PLIK_STRATEGII)
    raw_market = wczytaj_json(PLIK_RYNKU)

    # Konwersja Strategii
    baza_pozycji = {}
    if isinstance(raw_strategies, list):
        for item in raw_strategies:
            klucz = item.get("nazwa") or f"{item.get('symbol')}_{int(time.time())}"
            baza_pozycji[klucz] = item
    elif isinstance(raw_strategies, dict):
        baza_pozycji = raw_strategies

    # Konwersja Rynku
    rynek = {}
    if isinstance(raw_market, list):
        for item in raw_market:
            sym = item.get("symbol") or item.get("coin")
            if sym: rynek[sym] = item
    elif isinstance(raw_market, dict):
        if "data" in raw_market: rynek = raw_market["data"]
        elif "prices" in raw_market: 
             for p in raw_market["prices"]:
                 rynek[p["symbol"]] = {"price": p["current_price"]}

    if not baza_pozycji:
        print("   (Brak aktywnych pozycji)")
        return

    teraz = time.time()
    keys = list(baza_pozycji.keys())
    
    for klucz in keys:
        pozycja = baza_pozycji[klucz]
        if pozycja.get("status") not in ["OTWARTA", "aktywna"]: continue
        
        symbol = pozycja.get("symbol")
        typ = str(pozycja.get('typ', 'STANDARD')).lower()
        sym_short = symbol.replace("USDT", "")

        # --- DANE ---
        cena_akt = 0.0
        rsi_akt = 50.0
        vol_ratio = 1.0

        dane_coin = rynek.get(symbol) or rynek.get(sym_short) or {}

        # Pobieranie Ceny/RSI/Vol
        if "price" in dane_coin: cena_akt = float(dane_coin["price"])
        elif "lastPrice" in dane_coin: cena_akt = float(dane_coin["lastPrice"])
        elif "current_price" in dane_coin: cena_akt = float(dane_coin["current_price"])
        elif "1h" in dane_coin and dane_coin["1h"]: cena_akt = float(dane_coin["1h"][-1]["c"])
        
        if "rsi" in dane_coin: rsi_akt = float(dane_coin["rsi"])
        if "volume_ratio" in dane_coin: vol_ratio = float(dane_coin["volume_ratio"])
        elif "vol_ratio" in dane_coin: vol_ratio = float(dane_coin["vol_ratio"])

        if cena_akt == 0 and "prices" in raw_market:
             for p in raw_market["prices"]:
                 if p.get("symbol") == symbol:
                     cena_akt = float(p.get("current_price", 0))
                     break

        if cena_akt <= 0:
            print(f"   ⚠️ {symbol}: Brak ceny.")
            continue

        c_start = float(pozycja.get('cena_wejscia') or pozycja.get('cena_start') or 0)
        c_time = float(pozycja.get('czas_wejscia') or pozycja.get('czas_start_ts') or 0)
        
        if c_start == 0: continue
        
        # Obliczenia
        wynik = ((cena_akt - c_start) / c_start) * 100
        czas_min = (teraz - c_time) / 60
        
        # Update Max Zysk
        max_zysk = float(pozycja.get('max_zysk', 0.0))
        zmieniono_max = False
        if wynik > max_zysk:
            max_zysk = wynik
            pozycja['max_zysk'] = max_zysk
            zmieniono_max = True

        kolor = "🟢" if wynik > 0 else "🔴"
        print(f"   📊 {symbol:<6} [{typ:<4}] | {kolor} {wynik:>+6.2f}% (Max:{max_zysk:.1f}%) | RSI:{rsi_akt:.0f} Vol:{vol_ratio:.1f}x")

        # ==============================
        # ⚔️ GŁÓWNA LOGIKA DECYZYJNA
        # ==============================
        akcja = None
        powod = ""
        ikona_akcji = "❓"

        # Limity Czasowe
        limit_czasu = 65 
        grace_time = 30
        if "4h" in typ: limit_czasu = 245; grace_time = 60
        elif "1d" in typ: limit_czasu = 1450; grace_time = 120
        elif "tyg" in typ: limit_czasu = 10090; grace_time = 360

        # 1. TIMEOUT (PRIORYTET)
        if czas_min >= limit_czasu:
            # Wyjątek Grace Period (Mała strata + Niskie RSI)
            if -1.5 < wynik < 0 and rsi_akt < 30 and czas_min < (limit_czasu + grace_time):
                pass 
            else:
                akcja = "KONIEC CZASU"
                powod = f"Minęło {limit_czasu}m (Limit)"
                ikona_akcji = "⌛"

        # 2. HARD STOP LOSS (Globalny)
        elif wynik <= HARD_STOP_LOSS:
            # Safety check: Dead Cat Bounce (RSI < 20)
            if rsi_akt < 20 and wynik > (HARD_STOP_LOSS - 2.0):
                pass # Czekamy
            else:
                akcja = "HARD STOP LOSS"
                powod = f"Globalna Ochrona {HARD_STOP_LOSS}%"
                ikona_akcji = "💀"

        # 3. MOONSHOT TP (Globalny)
        elif wynik >= HARD_TAKE_PROFIT:
            akcja = "MOONSHOT TP"
            powod = f"Target {wynik:.2f}%"
            ikona_akcji = "🚀"

        # 4. SMART TRAILING (Globalny)
        elif max_zysk >= TRAILING_START_BIG and wynik < (max_zysk - TRAILING_DROP_BIG):
            akcja = "SMART TRAILING (BIG)"
            powod = "Korekta ze szczytu"
            ikona_akcji = "💰"
        elif max_zysk >= TRAILING_START_MIN and wynik < (max_zysk - TRAILING_DROP_SMALL):
            akcja = "SMART TRAILING (SMALL)"
            powod = "Szybka realizacja"
            ikona_akcji = "🛡️"

        # 5. LOGIKA "3 ŚWIATÓW" (Specyficzna)
        # Jeśli globalne zasady nie zadziałały, pytamy "Mózg Szczegółowy"
        if not akcja:
            czy_zamknac, powod_szczegolowy = ocen_pozycje(pozycja, cena_akt, rsi_akt, vol_ratio)
            if czy_zamknac:
                akcja = "ANALIZA RYNKU"
                powod = powod_szczegolowy
                ikona_akcji = "📉" if "SL" in powod or "CUT" in powod else "💰"

        # --- EGZEKUCJA ---
        if akcja:
            zysk_usdt = pm.zwroc_srodki(symbol, cena_akt)
            kolor_kasy = "🟢" if zysk_usdt > 0 else "🔴"

            print("\n" + "="*50)
            print(f"🔔 GŁÓWNY BOT: ZAMYKAM {symbol} [{typ}]")
            print(f"   📉 Akcja:        {akcja}")
            print(f"   ⏱️ Czas trwania: {czas_min:.0f} min")
            print(f"   💵 Cena wejścia: {c_start:.4f}")
            print(f"   💵 Cena wyjścia: {cena_akt:.4f}")
            print(f"   💰 WYNIK:        {ikona_akcji} {wynik:+.2f}% (Max: {max_zysk:+.2f}%)")
            print(f"   📝 Powód:        {powod}")
            print(f"   🏦 PORTFEL:      {kolor_kasy} {zysk_usdt:+.2f} USDT")
            print("="*50 + "\n")
            
            # NATYCHMIASTOWE USUNIĘCIE I ZAPIS
            del baza_pozycji[klucz]
            zapisz_json(PLIK_STRATEGII, baza_pozycji)
            print("   💾 Baza zaktualizowana natychmiast.")
        
        elif zmieniono_max:
             zapisz_json(PLIK_STRATEGII, baza_pozycji)

if __name__ == "__main__":
    main()