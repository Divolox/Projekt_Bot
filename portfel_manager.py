import json
import os
import time
import random

# ==========================================
# 🏦 SYSTEM FINANSOWY V2 (Bezpieczny zapis)
# ==========================================

PLIK_PORTFELA = "portfel.json"
PROWIZJA_BINANCE = 0.00075  
START_SALDO = 1000.00       

def wczytaj_portfel():
    """Wczytuje stan konta. Ponawia próby w razie blokady pliku."""
    # Próbujemy 5 razy zanim się poddamy (zabezpieczenie przed resetem)
    for i in range(5):
        if os.path.exists(PLIK_PORTFELA):
            try:
                with open(PLIK_PORTFELA, "r") as f:
                    dane = json.load(f)
                    # Walidacja
                    if "saldo_gotowka" not in dane: dane["saldo_gotowka"] = START_SALDO
                    if "pozycje" not in dane: dane["pozycje"] = {}
                    return dane
            except Exception:
                # Jeśli błąd (np. plik zajęty), czekamy losowy ułamek sekundy
                time.sleep(random.uniform(0.1, 0.3))
                continue
    
    # Jeśli po 5 próbach dalej nie działa, dopiero wtedy (ostateczność) lub jeśli plik nie istnieje
    if not os.path.exists(PLIK_PORTFELA):
        nowy_portfel = {
            "saldo_gotowka": START_SALDO,
            "historia_transakcji": 0,
            "pozycje": {}
        }
        zapisz_portfel(nowy_portfel)
        return nowy_portfel
    
    # Jeśli plik istnieje ale jest uszkodzony, zwracamy pusty (ale nie nadpisujemy od razu)
    return {"saldo_gotowka": 0, "pozycje": {}} 

def zapisz_portfel(dane):
    """Zapisuje stan konta. Ponawia próby."""
    for i in range(5):
        try:
            # Zapis tymczasowy + podmiana (atomowy zapis) jest bezpieczniejszy
            tmp_file = PLIK_PORTFELA + ".tmp"
            with open(tmp_file, "w") as f:
                json.dump(dane, f, indent=2)
            
            # W Windows replace może się wywalić jak plik zajęty, w Linux (Termux) jest atomowy
            os.replace(tmp_file, PLIK_PORTFELA)
            return
        except Exception:
            time.sleep(random.uniform(0.1, 0.3))
            continue

def oblicz_wartosc_total():
    portfel = wczytaj_portfel()
    wartosc_aktywow = sum([p['wartosc_wejscia'] for p in portfel.get('pozycje', {}).values()])
    return portfel.get("saldo_gotowka", 0) + wartosc_aktywow

def pobierz_srodki(symbol, aktualna_cena, procent_kapitalu=0.10, zrodlo="MAIN_BOT"):
    portfel = wczytaj_portfel()
    
    # Zabezpieczenie przed pustym odczytem
    if "saldo_gotowka" not in portfel: return False, 0, 0

    wartosc_aktywow = sum([p['wartosc_wejscia'] for p in portfel['pozycje'].values()])
    wartosc_total = portfel["saldo_gotowka"] + wartosc_aktywow
    
    stawka = wartosc_total * procent_kapitalu
    if stawka < 10: stawka = 10 
    
    if portfel["saldo_gotowka"] >= stawka:
        prowizja = stawka * PROWIZJA_BINANCE
        netto_usdt = stawka - prowizja
        ilosc_coinow = netto_usdt / aktualna_cena
        
        portfel["saldo_gotowka"] -= stawka
        portfel["pozycje"][symbol] = {
            "cena_wejscia": aktualna_cena,
            "ilosc_coinow": ilosc_coinow,
            "wartosc_wejscia": stawka,
            "timestamp_wejscia": time.time(),
            "zrodlo": zrodlo,
            "max_zysk": 0.0
        }
        zapisz_portfel(portfel)
        return True, ilosc_coinow, stawka
    
    return False, 0, 0

def zwroc_srodki(symbol, cena_wyjscia):
    portfel = wczytaj_portfel()
    
    if symbol in portfel.get("pozycje", {}):
        pos = portfel["pozycje"][symbol]
        
        wartosc_brutto = pos["ilosc_coinow"] * cena_wyjscia
        wartosc_netto = wartosc_brutto * (1 - PROWIZJA_BINANCE)
        
        portfel["saldo_gotowka"] += wartosc_netto
        if "historia_transakcji" in portfel:
            portfel["historia_transakcji"] += 1
        
        zysk_usdt = wartosc_netto - pos["wartosc_wejscia"]
        
        del portfel["pozycje"][symbol]
        zapisz_portfel(portfel)
        return zysk_usdt
    
    return 0.0