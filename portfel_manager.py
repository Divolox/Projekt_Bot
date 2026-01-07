import json
import os
import time
import sys

# ==========================================
# 💰 PORTFEL MANAGER (WERSJA ORYGINALNA + FIXY)
# ==========================================

PLIK_PORTFELA = "portfel.json"
PLIK_RYNKU = "rynek.json"

# Automatyczne szukanie pliku (żeby Skaner nie tworzył duplikatów)
if not os.path.exists(PLIK_PORTFELA) and os.path.exists(os.path.join("..", PLIK_PORTFELA)):
    PLIK_PORTFELA = os.path.join("..", PLIK_PORTFELA)
    PLIK_RYNKU = os.path.join("..", PLIK_RYNKU)

# --- [DODANE 1] Import funkcji do czyszczenia pamięci mózgu ---
try:
    # Dodajemy bieżący folder do ścieżki, żeby znaleźć data_storage
    sys.path.append(os.path.dirname(os.path.abspath(__file__))) 
    from data_storage import aktualizuj_status_strategii
except ImportError:
    # Zabezpieczenie, żeby się nie wywalił, jak nie znajdzie pliku
    def aktualizuj_status_strategii(symbol, status, wynik): pass
# -------------------------------------------------------------

def wczytaj_portfel():
    """Tę funkcję woła Twój Skaner. Musi tu być."""
    if not os.path.exists(PLIK_PORTFELA):
        dane = {
            "saldo_gotowka": 1000.0, 
            "pozycje": {},
            "historia": []
        }
        zapisz_portfel(dane)
        return dane
    try:
        with open(PLIK_PORTFELA, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {"saldo_gotowka": 1000.0, "pozycje": {}}

def zapisz_portfel(dane):
    """Tę funkcję woła Twój Skaner. Musi tu być."""
    try:
        with open(PLIK_PORTFELA, 'w', encoding='utf-8') as f:
            json.dump(dane, f, indent=4)
    except Exception as e:
        print(f"⚠️ Błąd zapisu: {e}")

def pobierz_cene_aktualna(symbol):
    """Pomocnicza funkcja do liczenia wartości portfela"""
    if not os.path.exists(PLIK_RYNKU): return 0.0
    try:
        with open(PLIK_RYNKU, 'r', encoding='utf-8') as f:
            rynek = json.load(f)
            
        # 1. Format listy (BotObserwator)
        if "prices" in rynek and isinstance(rynek["prices"], list):
            for p in rynek["prices"]:
                if p.get("symbol") == symbol: return float(p.get("current_price", 0))
        
        # 2. Format słownika (Stary)
        if "data" in rynek:
            if symbol in rynek["data"]:
                val = rynek["data"][symbol]
                return float(val.get("lastPrice", 0)) if isinstance(val, dict) else float(val)
            short = symbol.replace("USDT", "")
            if short in rynek["data"]:
                val = rynek["data"][short]
                return float(val.get("lastPrice", 0)) if isinstance(val, dict) else float(val)
    except: pass
    return 0.0

def oblicz_wartosc_total():
    """
    To naprawia błąd wyświetlania salda.
    Sumuje: Gotówka + Wartość Coinów
    """
    portfel = wczytaj_portfel()
    
    # Pobierz gotówkę
    wolne = float(portfel.get("saldo_gotowka", portfel.get("saldo_usdt", 0)))
    wartosc_pozycji = 0.0
    
    pozycje = portfel.get("pozycje", {})
    for symbol, dane in pozycje.items():
        # Ilość (obsługa starego i nowego formatu)
        ilosc = float(dane.get("ilosc", 0))
        if ilosc == 0: ilosc = float(dane.get("ilosc_coinow", 0))
        
        cena_wej = float(dane.get("cena_wejscia", 0))
        cena_akt = pobierz_cene_aktualna(symbol)
        
        # Jak brak ceny rynkowej, bierzemy cenę zakupu (żeby saldo nie spadało sztucznie)
        if cena_akt <= 0: cena_akt = cena_wej
            
        wartosc_pozycji += (ilosc * cena_akt)
        
    return wolne + wartosc_pozycji

def pobierz_srodki(symbol, cena_akt, procent_kapitalu=0.10, zrodlo="SKANER"):
    portfel = wczytaj_portfel()
    saldo = float(portfel.get("saldo_gotowka", portfel.get("saldo_usdt", 0)))
    
    # Limit slotów Skanera
    if zrodlo == "SKANER":
        aktywne = len([k for k, v in portfel.get("pozycje", {}).items() if v.get("zrodlo") == "SKANER"])
        if aktywne >= 7: return False, 0, 0
    
    # Kwota inwestycji
    if zrodlo == "MAIN_BOT":
        kwota = min(saldo, 100.0) # Stała kwota dla Main Bota
    else:
        # Skaner bierze % z całego kapitału (nie tylko wolnego)
        total = oblicz_wartosc_total()
        kwota = total * 0.10 

    if kwota > saldo: kwota = saldo
    if kwota < 11: return False, 0, 0

    ilosc_kupiona = kwota / cena_akt
    
    # Aktualizacja
    portfel["saldo_gotowka"] = saldo - kwota
    if "saldo_usdt" in portfel: portfel["saldo_usdt"] = portfel["saldo_gotowka"]
    
    nowa_pozycja = {
        "symbol": symbol,
        "ilosc": ilosc_kupiona,
        "ilosc_coinow": ilosc_kupiona, # Dublujemy dla pewności
        "cena_wejscia": cena_akt,
        "wartosc_wejscia": kwota,
        "czas_zakupu": time.time(),
        "zrodlo": zrodlo,
        "typ_strategii": "skalp" if zrodlo == "SKANER" else "swing"
    }
    
    portfel["pozycje"][symbol] = nowa_pozycja
    zapisz_portfel(portfel)
    
    return True, ilosc_kupiona, kwota

def zwroc_srodki(symbol, cena_wyjscia, zrodlo=None):
    portfel = wczytaj_portfel()
    
    if symbol not in portfel["pozycje"]: return 0.0
        
    poz = portfel["pozycje"][symbol]
    ilosc = float(poz.get("ilosc", 0))
    if ilosc == 0: ilosc = float(poz.get("ilosc_coinow", 0))
    
    wartosc_wyjscia = ilosc * cena_wyjscia
    wartosc_wejscia = float(poz.get("wartosc_wejscia", ilosc * float(poz.get("cena_wejscia", 0))))
    zysk_netto = wartosc_wyjscia - wartosc_wejscia
    
    # Zwrot
    saldo_obecne = float(portfel.get("saldo_gotowka", portfel.get("saldo_usdt", 0)))
    nowe_saldo = saldo_obecne + wartosc_wyjscia
    portfel["saldo_gotowka"] = nowe_saldo
    if "saldo_usdt" in portfel: portfel["saldo_usdt"] = nowe_saldo
    
    # Usunięcie
    del portfel["pozycje"][symbol]
    
    # Historia (opcjonalnie, żeby był ślad)
    if "historia" not in portfel: portfel["historia"] = []
    wpis = {
        "symbol": symbol,
        "zysk": zysk_netto,
        "czas": time.strftime('%Y-%m-%d %H:%M:%S')
    }
    portfel["historia"].append(wpis)
    
    zapisz_portfel(portfel)
    return zysk_netto

# --- [DODANE 1] Import funkcji do czyszczenia pamięci mózgu ---
try:
    # Dodajemy bieżący folder do ścieżki, żeby znaleźć data_storage
    sys.path.append(os.path.dirname(os.path.abspath(__file__))) 
    from data_storage import aktualizuj_status_strategii
except ImportError:
    # Zabezpieczenie, żeby się nie wywalił, jak nie znajdzie pliku
    def aktualizuj_status_strategii(symbol, status, wynik): pass
# -------------------------------------------------------------

# Inicjalizacja przy imporcie (żeby plik istniał)
if not os.path.exists(PLIK_PORTFELA):
    dane_start = {"saldo_gotowka": 1000.0, "pozycje": {}}
    zapisz_portfel(dane_start)
