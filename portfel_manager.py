import json
import os
import time
import sys

# ==========================================
# 💰 PORTFEL MANAGER (WERSJA SQLITE - FINAL)
# ==========================================

# Dodajemy ścieżkę do modułów
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Importujemy naszą nową bazę
try:
    from database_handler import DatabaseHandler
    db = DatabaseHandler() # Połączenie z bazą
    print("✅ Portfel połączony z bazą SQLite.")
except ImportError:
    print("❌ BŁĄD KRYTYCZNY: Brak pliku database_handler.py!")
    sys.exit()

# --- MIGRACJA STARYCH DANYCH (Tylko raz) ---
# Przepisuje saldo z portfel.json do bazy przy pierwszym starcie
def migruj_z_jsona():
    plik_json = "portfel.json"
    if os.path.exists(plik_json):
        try:
            with open(plik_json, 'r') as f:
                dane = json.load(f)
                stare_saldo = float(dane.get("saldo_gotowka", 1000.0))
                
                # Sprawdzamy obecne saldo w bazie
                obecne_db = db.pobierz_saldo()[0]
                
                # Jeśli w bazie jest domyślne 1000, a w jsonie inne, to nadpisujemy
                if obecne_db == 1000.0 and stare_saldo != 1000.0:
                    roznica = stare_saldo - 1000.0
                    db.aktualizuj_saldo(roznica)
                    print(f"🔄 Zmigrowano saldo z JSON do SQL: {stare_saldo} USDT")
        except: pass

migruj_z_jsona()
# -------------------------------------------

PLIK_RYNKU = "rynek.json"
# Obsługa ścieżki (czy jesteśmy w folderze skanera czy głównym)
if not os.path.exists(PLIK_RYNKU) and os.path.exists(os.path.join("..", PLIK_RYNKU)):
    PLIK_RYNKU = os.path.join("..", PLIK_RYNKU)


def pobierz_cene_aktualna(symbol):
    # Ceny nadal bierzemy z JSONa (bo BotObserwator tam zrzuca dane z giełdy)
    if not os.path.exists(PLIK_RYNKU): return 0.0
    try:
        with open(PLIK_RYNKU, 'r', encoding='utf-8') as f:
            rynek = json.load(f)
            
        if "prices" in rynek and isinstance(rynek["prices"], list):
            for p in rynek["prices"]:
                if p.get("symbol") == symbol: return float(p.get("current_price", 0))
        
        if "data" in rynek:
            symbol_short = symbol.replace("USDT", "")
            if symbol in rynek["data"]:
                val = rynek["data"][symbol]
                return float(val.get("lastPrice", 0)) if isinstance(val, dict) else float(val)
            if symbol_short in rynek["data"]:
                val = rynek["data"][symbol_short]
                return float(val.get("lastPrice", 0)) if isinstance(val, dict) else float(val)
    except: pass
    return 0.0

def oblicz_wartosc_total():
    # 1. Gotówka z bazy
    saldo_gotowka = db.pobierz_saldo()[0]
    
    # 2. Wartość pozycji z bazy
    wartosc_pozycji = 0.0
    
    try:
        # Pobieramy symbol i ilość wszystkich aktywnych pozycji
        db.cursor.execute("SELECT symbol, ilosc FROM aktywne_pozycje")
        pozycje = db.cursor.fetchall()
        
        for sym, ilosc in pozycje:
            cena_akt = pobierz_cene_aktualna(sym)
            # Jeśli nie mamy ceny aktualnej, bierzemy cenę wejścia z bazy
            if cena_akt == 0:
                db.cursor.execute("SELECT cena_wejscia FROM aktywne_pozycje WHERE symbol=?", (sym,))
                res = db.cursor.fetchone()
                if res: cena_akt = res[0]
            
            wartosc_pozycji += (ilosc * cena_akt)
            
    except Exception as e:
        print(f"⚠️ Błąd obliczania total: {e}")

    return saldo_gotowka + wartosc_pozycji

# Funkcja dla kompatybilności wstecznej (niektóre moduły mogą jej szukać, np. Skaner)
# Skaner myśli, że dostaje JSONa, a my mu budujemy słownik z danych SQL. Magia.
def wczytaj_portfel():
    saldo = db.pobierz_saldo()[0]
    
    db.cursor.execute("SELECT symbol, ilosc, cena_wejscia, zrodlo, typ_strategii, czas_wejscia, unikalne_id FROM aktywne_pozycje")
    rows = db.cursor.fetchall()
    pozycje_dict = {}
    
    for r in rows:
        # Kluczem w starym portfelu był symbol (np. BTCUSDT)
        # UWAGA: Jeśli mamy 2 strategie na BTC, stary system widziałby tylko jedną.
        # Ale Skaner i tak ma swoje unikalne ID.
        sym = r[0]
        pozycje_dict[sym] = {
            "symbol": sym, 
            "ilosc": r[1], 
            "cena_wejscia": r[2], 
            "zrodlo": r[3], 
            "typ_strategii": r[4], 
            "czas_zakupu": r[5],
            "max_zysk": 0.0 # Baza tego nie trzyma domyślnie, ale Skanerowi damy 0 na start
        }
    
    return {
        "saldo_gotowka": saldo,
        "saldo_usdt": saldo,
        "pozycje": pozycje_dict
    }

# Funkcja zapisu (dla kompatybilności - nic nie robi, bo SQL zapisuje na bieżąco)
def zapisz_portfel(dane):
    pass 

# =========================================================
# 🔥 GŁÓWNA FUNKCJA ZAKUPOWA (Z NASZYM FIXEM TYPU)
# =========================================================
def pobierz_srodki(symbol, cena_akt, procent_kapitalu=0.10, zrodlo="SKANER", typ_strategii="STANDARD"):
    # 1. Sprawdzenie salda w SQL
    saldo = db.pobierz_saldo()[0]
    
    # Limit slotów dla Skanera
    if zrodlo == "SKANER":
        db.cursor.execute("SELECT count(*) FROM aktywne_pozycje WHERE zrodlo='SKANER'")
        aktywne_cnt = db.cursor.fetchone()[0]
        if aktywne_cnt >= 7: return False, 0, 0
    
    if zrodlo == "MAIN_BOT":
        kwota = min(saldo, 100.0)
    else:
        total = oblicz_wartosc_total()
        kwota = total * 0.10 

    if kwota > saldo: kwota = saldo
    if kwota < 11: return False, 0, 0

    ilosc_kupiona = kwota / cena_akt
    
    # 2. Transakcja w SQL
    try:
        # 🔥 FIX: Ustalanie finalnego typu (skalp vs jednodniowa/tygodniowa itd.)
        finalny_typ = "skalp" if zrodlo == "SKANER" else typ_strategii
        
        # Odejmij środki (ujemna kwota)
        db.aktualizuj_saldo(-kwota)
        
        # Dodaj pozycję do bazy
        # (DatabaseHandler sam stworzy unikalne ID np. BTC_jednodniowa)
        sukces = db.dodaj_pozycje(symbol, finalny_typ, cena_akt, ilosc_kupiona, zrodlo, "Kupno")
        
        if sukces:
            return True, ilosc_kupiona, kwota
        else:
            # Rollback (oddaj kasę jak się nie udało dodać pozycji - np. duplikat)
            db.aktualizuj_saldo(kwota)
            return False, 0, 0
            
    except Exception as e:
        print(f"⚠️ Błąd SQL przy zakupie: {e}")
        return False, 0, 0

# =========================================================
# 🔥 FUNKCJA SPRZEDAŻY
# =========================================================
def zwroc_srodki(symbol, cena_wyjscia, zrodlo=None):
    try:
        # Pobieramy pozycje dla danego symbolu
        db.cursor.execute("SELECT * FROM aktywne_pozycje WHERE symbol=?", (symbol,))
        rows = db.cursor.fetchall()
        
        if not rows: return 0.0
        
        # Wybieramy właściwą pozycję
        # rows to: unikalne_id, symbol, typ, cena_wej, ilosc, czas... (zobacz database_handler)
        poz = None
        for r in rows:
            # r[6] to zrodlo w mojej strukturze tabeli
            if zrodlo == "SKANER" and r[6] == "SKANER": poz = r; break
            if zrodlo != "SKANER" and r[6] != "SKANER": poz = r; break
            
        if not poz: poz = rows[0] # Fallback
        
        # Rozpakuj dane z SQL
        unikalne_id = poz[0]
        typ_strat = poz[2]
        cena_wej = poz[3]
        ilosc = poz[4]
        
        wartosc_wyjscia = ilosc * cena_wyjscia
        wartosc_wejscia = ilosc * cena_wej
        zysk_netto = wartosc_wyjscia - wartosc_wejscia
        zysk_proc = ((cena_wyjscia - cena_wej) / cena_wej) * 100
        
        # 1. Usuń pozycję z aktywnych
        db.usun_pozycje(symbol, typ_strat)
        
        # 2. Dodaj kasę do salda
        db.aktualizuj_saldo(wartosc_wyjscia)
        
        # 3. Zapisz w historii (Archiwum)
        db.zapisz_historie_transakcji(symbol, typ_strat, zysk_netto, zysk_proc, "Sprzedaż")
        
        # 4. Aktualizuj Mózg (Feedback Loop)
        if zrodlo != "SKANER":
            db.aktualizuj_strategie_mozgu(symbol, typ_strat, zysk_proc, "ZAKONCZONA")
            print(f"   💾 [SQL] Zaktualizowano inteligencję dla {symbol} ({zysk_proc:.2f}%)")

        return zysk_netto

    except Exception as e:
        print(f"⚠️ Błąd SQL przy sprzedaży: {e}")
        return 0.0