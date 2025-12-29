import json
import time
import requests
import os

# --- KONFIGURACJA ---
PLIK_STRATEGII = "strategie.json"

# --- ZASADY WYJŚCIA (UPGRADE) ---
HARD_STOP_LOSS = -4.0         # Twarda odcinka straty
HARD_TAKE_PROFIT = 20.0       # Moonshot (Bierze kasę bez gadania jak wystrzeli)

# Smart Trailing (Dynamiczne zamykanie)
TRAILING_START_MIN = 1.5      # Zaczynamy śledzić od 1.5% zysku
TRAILING_DROP_SMALL = 0.5     # Dla małych zysków: zamykamy jak spadnie o 0.5% od szczytu

TRAILING_START_BIG = 5.0      # Próg "Dużego Zysku"
TRAILING_DROP_BIG = 1.5       # Dla dużych zysków: zamykamy jak spadnie o 1.5% od szczytu

def pobierz_cene(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        return float(data['price'])
    except Exception as e:
        # Cicha obsługa błędu, żeby nie śmiecić w logach co 5 min
        return None

def main():
    # Sprawdzamy czy baza istnieje
    if not os.path.exists(PLIK_STRATEGII):
        return

    try:
        with open(PLIK_STRATEGII, "r") as f:
            baza = json.load(f)
    except:
        return

    if not baza: return

    teraz = time.time()
    do_usuniecia = []
    zmieniono_baze = False
    
    # print(f"🛡️ EVALUATOR: Weryfikacja {len(baza)} pozycji...") 

    for klucz, pozycja in baza.items():
        if pozycja.get("status") != "OTWARTA":
            continue

        symbol = pozycja['symbol']
        typ = pozycja['typ'] # np. 1h, 4h
        
        # Obsługa stringów/floatów w JSON (dla pewności)
        try:
            cena_wejscia = float(pozycja['cena_wejscia'])
            czas_wejscia = float(pozycja['czas_wejscia'])
        except: continue

        # 1. Pobieramy aktualną cenę
        cena_akt = pobierz_cene(symbol)
        if cena_akt is None: continue

        # 2. Liczymy matematykę
        wynik_procent = ((cena_akt - cena_wejscia) / cena_wejscia) * 100
        czas_trwania_min = (teraz - czas_wejscia) / 60
        
        # 3. Aktualizacja MAX ZYSKU (Pamięć o szczycie)
        max_zysk = float(pozycja.get('max_zysk', 0.0))
        # Jeśli wynik jest lepszy niż max_zysk, aktualizujemy
        if wynik_procent > max_zysk:
            max_zysk = wynik_procent
            pozycja['max_zysk'] = max_zysk
            zmieniono_baze = True
        
        # --- LOGIKA DECYZYJNA (Twoje zasady) ---
        akcja = None
        powod = ""
        ikona = "❓"

        # A. HARD STOP LOSS (Ochrona dupy)
        if wynik_procent <= HARD_STOP_LOSS:
            akcja = "HARD STOP LOSS"
            powod = f"Ochrona kapitału: {wynik_procent:.2f}%"
            ikona = "💀"

        # B. HARD TAKE PROFIT (Moonshot)
        elif wynik_procent >= HARD_TAKE_PROFIT:
            akcja = "MOONSHOT TP"
            powod = f"Zysk docelowy osiągnięty: {wynik_procent:.2f}%"
            ikona = "🚀"

        # C. SMART TRAILING (Upgrade)
        # Sytuacja 1: Duży zysk (>5%), tolerujemy spadek o 1.5%
        elif max_zysk >= TRAILING_START_BIG:
            if wynik_procent < (max_zysk - TRAILING_DROP_BIG):
                akcja = "SMART TRAILING (BIG)"
                powod = f"Korekta ze szczytu {max_zysk:.2f}% -> {wynik_procent:.2f}%"
                ikona = "💰"
        
        # Sytuacja 2: Mały zysk (>1.5%), tolerujemy spadek o 0.5%
        elif max_zysk >= TRAILING_START_MIN:
            if wynik_procent < (max_zysk - TRAILING_DROP_SMALL):
                akcja = "SMART TRAILING (SMALL)"
                powod = f"Szybka realizacja: {max_zysk:.2f}% -> {wynik_procent:.2f}%"
                ikona = "🛡️"

        # D. TIME EXIT (Koniec czasu)
        limit_czasu = 240 if "4h" in str(typ) else 60
        
        if not akcja and czas_trwania_min >= limit_czasu:
            # Warunek specjalny: Jeśli jesteśmy na lekkim minusie (-1.5% do 0%),
            # a minął czas, dajemy mu jeszcze 30 min szansy.
            if -1.5 < wynik_procent < 0 and czas_trwania_min < (limit_czasu + 30):
                pass 
            else:
                akcja = "KONIEC CZASU"
                powod = f"Minęło {limit_czasu}m. Wynik: {wynik_procent:.2f}%"
                ikona = "⌛"

        # --- EGZEKUCJA ---
        if akcja:
            print("\n" + "="*50)
            print(f"🔔 GŁÓWNY BOT: ZAMYKAM {symbol} [{typ}]")
            print(f"   📉 Akcja: {akcja}")
            print(f"   ⏱️ Czas trwania: {czas_trwania_min:.0f} min")
            print(f"   💵 Cena wejścia: {cena_wejscia}")
            print(f"   💵 Cena wyjścia: {cena_akt}")
            print(f"   💰 WYNIK: {ikona} {wynik_procent:+.2f}% (Max był: {max_zysk:+.2f}%)")
            print(f"   📝 Powód: {powod}")
            print("="*50 + "\n")
            do_usuniecia.append(klucz)

    # Zapis zmian w pliku
    if do_usuniecia or zmieniono_baze:
        for k in do_usuniecia:
            if k in baza: del baza[k]
        
        try:
            with open(PLIK_STRATEGII, "w") as f:
                json.dump(baza, f, indent=4)
        except: pass

if __name__ == "__main__":
    main()

