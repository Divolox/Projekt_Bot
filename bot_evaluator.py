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

# --- ZASADY WYJŚCIA ---
HARD_STOP_LOSS = -5.0         
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

def main():
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 🛡️ EVALUATOR: Weryfikacja pozycji...")

    # 1. Wczytujemy dane
    raw_strategies = wczytaj_json(PLIK_STRATEGII)
    raw_market = wczytaj_json(PLIK_RYNKU)

    # === FIX: Konwersja Strategii (Lista -> Słownik) ===
    baza_pozycji = {}
    if isinstance(raw_strategies, list):
        for item in raw_strategies:
            klucz = item.get("nazwa") or f"{item.get('symbol')}_{int(time.time())}"
            baza_pozycji[klucz] = item
    elif isinstance(raw_strategies, dict):
        baza_pozycji = raw_strategies

    # === FIX: Konwersja Rynku (Lista -> Słownik) ===
    rynek = {}
    if isinstance(raw_market, list):
        for item in raw_market:
            sym = item.get("symbol") or item.get("coin")
            if sym:
                rynek[sym] = item
                if "price" not in item and "current_price" in item:
                     rynek[sym]["price"] = item["current_price"]
    elif isinstance(raw_market, dict):
        rynek = raw_market

    if not baza_pozycji:
        print("   (Brak aktywnych pozycji)")
        return

    teraz = time.time()
    do_usuniecia = []
    zmieniono_baze = False
    
    # Licznik aktywnych
    liczba_aktywnych = sum(1 for p in baza_pozycji.values() if p.get("status") in ["aktywna", "OTWARTA"])
    print(f"   ℹ️ Analizuję {liczba_aktywnych} aktywnych pozycji...")

    # 2. Pętla główna
    for klucz, pozycja in baza_pozycji.items():
        
        status = pozycja.get("status", "")
        if status not in ["OTWARTA", "aktywna"]:
            continue

        symbol = pozycja.get("symbol")
        dane_rynkowe = rynek.get(symbol, {})
        
        # Obsługa różnych nazw ceny w pliku rynku
        cena_akt = float(dane_rynkowe.get("price") or dane_rynkowe.get("lastPrice") or dane_rynkowe.get("current_price") or 0.0)

        if cena_akt <= 0:
            continue

        # Obsługa Twoich nazw (cena_start / cena_wejscia)
        cena_wejscia = float(pozycja.get('cena_wejscia') or pozycja.get('cena_start') or 0)
        czas_wejscia = float(pozycja.get('czas_wejscia') or pozycja.get('czas_start_ts') or 0)
        typ = pozycja.get('typ', 'STANDARD')

        if cena_wejscia == 0: continue

        # Obliczenia
        wynik_procent = ((cena_akt - cena_wejscia) / cena_wejscia) * 100
        czas_trwania_min = (teraz - czas_wejscia) / 60

        # Max Zysk
        max_zysk = float(pozycja.get('max_zysk', 0.0))
        if wynik_procent > max_zysk:
            max_zysk = wynik_procent
            pozycja['max_zysk'] = max_zysk
            zmieniono_baze = True 

        # --- WYŚWIETLANIE STATUSU (Twoja wersja) ---
        ikona = "🟢" if wynik_procent > 0 else "🔴"
        print(f"   📊 {symbol:<6} | {ikona} {wynik_procent:>+6.2f}% (Max: {max_zysk:>+6.2f}%) | {int(czas_trwania_min)}m")

        # LOGIKA
        akcja = None
        powod = ""
        ikona_akcji = "❓"

        if wynik_procent <= HARD_STOP_LOSS:
            akcja = "HARD STOP LOSS"
            powod = f"Ochrona kapitału: {wynik_procent:.2f}%"
            ikona_akcji = "💀"
        elif wynik_procent >= HARD_TAKE_PROFIT:
            akcja = "MOONSHOT TP"
            powod = f"Zysk docelowy: {wynik_procent:.2f}%"
            ikona_akcji = "🚀"
        elif max_zysk >= TRAILING_START_BIG and wynik_procent < (max_zysk - TRAILING_DROP_BIG):
            akcja = "SMART TRAILING (BIG)"
            powod = "Korekta ze szczytu"
            ikona_akcji = "💰"
        elif max_zysk >= TRAILING_START_MIN and wynik_procent < (max_zysk - TRAILING_DROP_SMALL):
            akcja = "SMART TRAILING (SMALL)"
            powod = "Szybka realizacja"
            ikona_akcji = "🛡️"

        # Limit czasu
        limit = 240 if "4h" in str(typ) or "4-godzinowa" in str(typ) else 60
        if not akcja and czas_trwania_min >= limit:
            if -1.5 < wynik_procent < 0 and czas_trwania_min < (limit + 30): pass
            else: 
                akcja = "KONIEC CZASU"
                powod = f"Minęło {limit}m"
                ikona_akcji = "⌛"

        # --- EGZEKUCJA (PEŁNY FORMAT GRAFICZNY) ---
        if akcja:
            zysk_usdt = pm.zwroc_srodki(symbol, cena_akt)
            kolor_kasy = "🟢" if zysk_usdt > 0 else "🔴"

            print("\n" + "="*50)
            print(f"🔔 GŁÓWNY BOT: ZAMYKAM {symbol} [{typ}]")
            print(f"   📉 Akcja:        {akcja}")
            print(f"   ⏱️ Czas trwania: {czas_trwania_min:.0f} min")
            print(f"   💵 Cena wejścia: {cena_wejscia:.4f}")
            print(f"   💵 Cena wyjścia: {cena_akt:.4f}")
            print(f"   💰 WYNIK:        {ikona_akcji} {wynik_procent:+.2f}% (Max był: {max_zysk:+.2f}%)")
            print(f"   📝 Powód:        {powod}")
            print(f"   🏦 PORTFEL:      {kolor_kasy} {zysk_usdt:+.2f} USDT wraca do puli.")
            print("="*50 + "\n")
            
            do_usuniecia.append(klucz)

    # Zapis (zachowujemy strukturę słownika dla porządku)
    if do_usuniecia or zmieniono_baze or isinstance(raw_strategies, list):
        for k in do_usuniecia:
            if k in baza_pozycji: del baza_pozycji[k]
        
        zapisz_json(PLIK_STRATEGII, baza_pozycji)

if __name__ == "__main__":
    main()