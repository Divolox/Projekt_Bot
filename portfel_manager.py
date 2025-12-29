import json
import os
import time

# ==========================================
# 🏦 SYSTEM FINANSOWY (PORTFEL MANAGER)
# ==========================================

PLIK_PORTFELA = "portfel.json"
PROWIZJA_BINANCE = 0.00075  # 0.075% (Standard z BNB)
START_SALDO = 1000.00       # Wirtualne saldo startowe

def wczytaj_portfel():
    """Wczytuje stan konta lub tworzy nowy portfel"""
    if os.path.exists(PLIK_PORTFELA):
        try:
            with open(PLIK_PORTFELA, "r") as f:
                dane = json.load(f)
                # Naprawa struktury w razie błędów
                if "saldo_gotowka" not in dane: dane["saldo_gotowka"] = START_SALDO
                if "pozycje" not in dane: dane["pozycje"] = {}
                return dane
        except: pass
    
    # Tworzenie czystego portfela
    nowy_portfel = {
        "saldo_gotowka": START_SALDO,
        "historia_transakcji": 0,
        "pozycje": {}
    }
    zapisz_portfel(nowy_portfel)
    return nowy_portfel

def zapisz_portfel(dane):
    try:
        with open(PLIK_PORTFELA, "w") as f: json.dump(dane, f, indent=2)
    except: pass

def oblicz_wartosc_total():
    """Zwraca: Gotówka + Wartość zakupu otwartych pozycji"""
    portfel = wczytaj_portfel()
    wartosc_aktywow = sum([p['wartosc_wejscia'] for p in portfel['pozycje'].values()])
    return portfel["saldo_gotowka"] + wartosc_aktywow

def pobierz_srodki(symbol, aktualna_cena, procent_kapitalu=0.10, zrodlo="MAIN_BOT"):
    """
    Pobiera środki na zakup.
    Zwraca: (True, ilosc_kupiona, koszt_usdt) lub (False, 0, 0)
    """
    portfel = wczytaj_portfel()
    
    # Liczymy 10% od CAŁEGO kapitału (żeby stawka rosła wraz z zyskami)
    wartosc_aktywow = sum([p['wartosc_wejscia'] for p in portfel['pozycje'].values()])
    wartosc_total = portfel["saldo_gotowka"] + wartosc_aktywow
    
    stawka = wartosc_total * procent_kapitalu
    if stawka < 10: stawka = 10 # Minimum 10 USDT
    
    # Sprawdzamy czy fizycznie mamy tyle gotówki
    if portfel["saldo_gotowka"] >= stawka:
        # Symulacja prowizji przy zakupie
        prowizja = stawka * PROWIZJA_BINANCE
        netto_usdt = stawka - prowizja
        ilosc_coinow = netto_usdt / aktualna_cena
        
        portfel["saldo_gotowka"] -= stawka
        
        # Rejestracja pozycji
        portfel["pozycje"][symbol] = {
            "cena_wejscia": aktualna_cena,
            "ilosc_coinow": ilosc_coinow,
            "wartosc_wejscia": stawka,
            "timestamp_wejscia": time.time(),
            "zrodlo": zrodlo,  # KLUCZOWE: "SKANER" lub "MAIN_BOT"
            "max_zysk": 0.0
        }
        zapisz_portfel(portfel)
        return True, ilosc_coinow, stawka
    
    return False, 0, 0

def zwroc_srodki(symbol, cena_wyjscia):
    """Zamyka pozycję i oddaje pieniądze do portfela"""
    portfel = wczytaj_portfel()
    
    if symbol in portfel["pozycje"]:
        pos = portfel["pozycje"][symbol]
        
        # Obliczenie wartości wyjścia
        wartosc_brutto = pos["ilosc_coinow"] * cena_wyjscia
        prowizja = wartosc_brutto * PROWIZJA_BINANCE
        wartosc_netto = wartosc_brutto - prowizja
        
        # Zwrot kasy
        portfel["saldo_gotowka"] += wartosc_netto
        portfel["historia_transakcji"] += 1
        
        zysk_usdt = wartosc_netto - pos["wartosc_wejscia"]
        
        del portfel["pozycje"][symbol]
        zapisz_portfel(portfel)
        
        return zysk_usdt
    
    return 0.0

