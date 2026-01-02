import json
import os
import time

PLIK_PORTFELA = "portfel.json"

def wczytaj_portfel():
    if not os.path.exists(PLIK_PORTFELA):
        # Tworzymy nowy portfel, jeśli nie istnieje
        startowy = {
            "saldo_gotowka": 1000.0,
            "saldo_poczatkowe": 1000.0,
            "pozycje": {},
            "historia": []
        }
        zapisz_portfel(startowy)
        return startowy
    try:
        with open(PLIK_PORTFELA, 'r') as f:
            dane = json.load(f)
            # --- FIX CHIRURGICZNY: Zabezpieczenie struktury ---
            if "historia" not in dane: dane["historia"] = []
            if "pozycje" not in dane: dane["pozycje"] = {}
            if "saldo_gotowka" not in dane: dane["saldo_gotowka"] = 1000.0
            return dane
    except:
        return {"saldo_gotowka": 1000.0, "pozycje": {}, "historia": []}

def zapisz_portfel(dane):
    try:
        with open(PLIK_PORTFELA, 'w') as f:
            json.dump(dane, f, indent=4)
    except Exception as e:
        print(f"⚠️ Błąd zapisu portfela: {e}")

def oblicz_wartosc_total():
    """
    Sumuje gotówkę + wartość WSZYSTKICH otwartych pozycji (Skaner + Main Bot).
    Naprawia błąd 'fałszywej straty' gdy Main Bot trzyma pozycje.
    """
    portfel = wczytaj_portfel()
    gotowka = portfel.get("saldo_gotowka", 0.0)
    wartosc_pozycji = 0.0
    
    # Sumujemy wartość wszystkich pozycji (ilość * cena wejścia)
    # To jest estymacja 'cost basis'. 
    # Dokładna wycena live jest w logach poszczególnych botów.
    for symbol, poz in portfel.get("pozycje", {}).items():
        # --- FIX: Bezpieczne pobieranie ilości ---
        ilosc = float(poz.get("ilosc", 0))
        cena_wejscia = float(poz.get("cena_wejscia", 0))
        
        # Jeśli ilość jest 0, próbujemy ratować z wartości
        if ilosc == 0 and cena_wejscia > 0:
             wartosc_wej = float(poz.get("wartosc_wejscia", 0))
             if wartosc_wej > 0: ilosc = wartosc_wej / cena_wejscia
             
        wartosc_pozycji += (ilosc * cena_wejscia)
        
    return gotowka + wartosc_pozycji

def pobierz_srodki(symbol, cena_aktualna, procent_kapitalu=0.10, zrodlo="SKANER"):
    portfel = wczytaj_portfel()
    saldo = portfel["saldo_gotowka"]
    
    # Main Bot ma inne zasady (stała kwota lub % całego portfela)
    # Skaner bierze % dostępnej gotówki
    
    kwota_inwestycji = saldo * procent_kapitalu
    
    # Zabezpieczenie minimalne (np. 11 USDT na Binance)
    if kwota_inwestycji < 12:
        kwota_inwestycji = 12
        
    if saldo < kwota_inwestycji:
        return False, 0, 0 # Brak środków

    ilosc_kupiona = kwota_inwestycji / cena_aktualna
    
    # Aktualizacja portfela
    portfel["saldo_gotowka"] -= kwota_inwestycji
    
    nowa_pozycja = {
        "symbol": symbol,
        "ilosc": ilosc_kupiona,
        "cena_wejscia": cena_aktualna,
        "wartosc_wejscia": kwota_inwestycji,
        "czas_zakupu": time.time(),
        "timestamp_wejscia": time.time(), # Dla Skanera
        "max_zysk": 0.0,
        "zrodlo": zrodlo # Ważne: Rozróżnia SKANER od MAIN_BOT
    }
    
    portfel["pozycje"][symbol] = nowa_pozycja
    zapisz_portfel(portfel)
    
    return True, ilosc_kupiona, kwota_inwestycji

def zwroc_srodki(symbol, cena_wyjscia, zrodlo=None):
    # Parametr 'zrodlo' jest opcjonalny dla kompatybilności wstecznej
    portfel = wczytaj_portfel()
    
    if symbol not in portfel["pozycje"]:
        return 0.0
        
    pozycja = portfel["pozycje"][symbol]
    
    # --- FIX: Bezpieczne pobieranie ilości (z ratunkiem) ---
    ilosc = float(pozycja.get("ilosc", 0))
    if ilosc == 0:
        c_wej = float(pozycja.get("cena_wejscia", 1))
        v_wej = float(pozycja.get("wartosc_wejscia", 0))
        if c_wej > 0: ilosc = v_wej / c_wej
    
    # Obliczamy wartość przy wyjściu
    wartosc_wyjscia = ilosc * cena_wyjscia
    zysk_netto = wartosc_wyjscia - float(pozycja.get("wartosc_wejscia", 0))
    
    # Aktualizacja salda
    portfel["saldo_gotowka"] += wartosc_wyjscia
    
    # Zapis historii
    wpis_historia = {
        "symbol": symbol,
        "zysk": zysk_netto,
        "procent": ((cena_wyjscia - float(pozycja.get("cena_wejscia", 1))) / float(pozycja.get("cena_wejscia", 1))) * 100,
        "zrodlo": pozycja.get("zrodlo", "NIEZNANE"),
        "czas": time.strftime('%Y-%m-%d %H:%M:%S')
    }
    
    # --- FIX: Zabezpieczenie przed brakiem listy historii ---
    if "historia" not in portfel: portfel["historia"] = []
    portfel["historia"].append(wpis_historia)
    
    # Usuwamy pozycję
    del portfel["pozycje"][symbol]
    
    zapisz_portfel(portfel)
    return zysk_netto