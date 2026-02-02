import json
import os
import time
import sys

# ============================================================
# 💰 PORTFEL MANAGER V10.12 (FULL USER CODE + CRITICAL FIXES)
# ============================================================

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

# --- MIGRACJA STARYCH DANYCH (Zachowane z Twojego kodu) ---
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
if not os.path.exists(PLIK_RYNKU) and os.path.exists(os.path.join("..", PLIK_RYNKU)):
    PLIK_RYNKU = os.path.join("..", PLIK_RYNKU)

def pobierz_cene_aktualna(symbol):
    if not os.path.exists(PLIK_RYNKU): return 0.0
    try:
        with open(PLIK_RYNKU, 'r', encoding='utf-8') as f:
            rynek = json.load(f)
            
        if "prices" in rynek and isinstance(rynek["prices"], list):
            for p in rynek["prices"]:
                if p.get("symbol") == symbol: return float(p.get("price", 0))
        
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
    try:
        saldo_gotowka = db.pobierz_saldo()[0]
    except: return 0.0
    
    # 2. Wartość pozycji z bazy
    wartosc_pozycji = 0.0
    
    try:
        db.cursor.execute("SELECT symbol, ilosc FROM aktywne_pozycje")
        pozycje = db.cursor.fetchall()
        
        for sym, ilosc in pozycje:
            cena_akt = pobierz_cene_aktualna(sym)
            if cena_akt == 0:
                db.cursor.execute("SELECT cena_wejscia FROM aktywne_pozycje WHERE symbol=?", (sym,))
                res = db.cursor.fetchone()
                if res: cena_akt = res[0]
            
            wartosc_pozycji += (ilosc * cena_akt)
            
    except Exception as e:
        print(f"⚠️ Błąd obliczania total: {e}")

    return saldo_gotowka + wartosc_pozycji

# Funkcja dla kompatybilności wstecznej (Zachowane dla Skanera)
def wczytaj_portfel():
    try:
        saldo = db.pobierz_saldo()[0]
        
        db.cursor.execute("SELECT symbol, ilosc, cena_wejscia, zrodlo, typ_strategii, czas_wejscia, unikalne_id FROM aktywne_pozycje")
        rows = db.cursor.fetchall()
        pozycje_dict = {}
        
        for r in rows:
            sym = r[0]
            # Skaner potrzebuje słownika, więc robimy mu symulację
            pozycje_dict[sym] = {
                "symbol": sym, 
                "ilosc": r[1], 
                "cena_wejscia": r[2], 
                "zrodlo": r[3], 
                "typ_strategii": r[4], 
                "czas_zakupu": r[5],
                "max_zysk": 0.0 
            }
        
        return {
            "saldo_gotowka": saldo,
            "saldo_usdt": saldo,
            "pozycje": pozycje_dict
        }
    except:
        return {"saldo_gotowka": 0, "pozycje": {}}

# Funkcja zapisu (Zachowane dla kompatybilności)
def zapisz_portfel(dane):
    pass 

# =========================================================
# 🔥 GŁÓWNA FUNKCJA ZAKUPOWA (FIX ARGUMENTU)
# =========================================================
def pobierz_srodki(symbol, cena_akt, procent_kapitalu=0.10, zrodlo="SKANER", typ_strategii="STANDARD"):
    # 1. Sprawdzenie salda w SQL
    try:
        saldo = db.pobierz_saldo()[0]
    except: return False, 0, 0
    
    # Limit slotów dla Skanera (10 - przywrócony Berserker)
    if zrodlo == "SKANER":
        try:
            db.cursor.execute("SELECT count(*) FROM aktywne_pozycje WHERE zrodlo='SKANER'")
            aktywne_cnt = db.cursor.fetchone()[0]
            if aktywne_cnt >= 10: return False, 0, 0
        except: pass
    
    if zrodlo == "MAIN_BOT" or zrodlo == "GŁÓWNY_BOT":
        # 1. Limit slotów (zwiększamy do 6, bo mamy więcej coinów)
        try:
            db.cursor.execute("SELECT count(*) FROM aktywne_pozycje WHERE zrodlo='MAIN_BOT' OR zrodlo='GŁÓWNY_BOT'")
            main_cnt = db.cursor.fetchone()[0]
            if main_cnt >= 6: return False, 0, 0
        except: pass

        # 2. Stawka 5% kapitału (bezpieczniej przy 9 coinach)
        total = oblicz_wartosc_total()
        kwota = total * 0.05
    else:
        total = oblicz_wartosc_total()
        kwota = total * procent_kapitalu 

    if kwota > saldo: kwota = saldo
    if kwota < 5: return False, 0, 0 # Minimum 5$ dla bezpieczeństwa

    ilosc_kupiona = kwota / cena_akt
    
    # 2. Transakcja w SQL
    try:
        # 🔥 FIX: Twój kod, który przywróciłem. 
        # Ustalamy finalny typ na podstawie źródła LUB argumentu
        finalny_typ = "skalp" if zrodlo == "SKANER" else typ_strategii
        
        # Odejmij środki
        db.aktualizuj_saldo(-kwota)
        
        # Dodaj pozycję (z użyciem finalny_typ!)
        sukces = db.dodaj_pozycje(symbol, finalny_typ, cena_akt, ilosc_kupiona, zrodlo, "Kupno")
        
        if sukces:
            return True, ilosc_kupiona, kwota
        else:
            db.aktualizuj_saldo(kwota)
            return False, 0, 0
            
    except Exception as e:
        print(f"⚠️ Błąd SQL przy zakupie: {e}")
        return False, 0, 0

# =========================================================
# 🔥 FUNKCJA SPRZEDAŻY (CRITICAL FIX: TYP_STRATEGII)
# =========================================================
# Tutaj musimy zmienić definicję, żeby przyjmowała typ_strategii
def zwroc_srodki(symbol, cena_wyjscia, zrodlo=None, typ_strategii=None):
    try:
        # Pobieramy pozycje dla danego symbolu
        db.cursor.execute("SELECT * FROM aktywne_pozycje WHERE symbol=?", (symbol,))
        rows = db.cursor.fetchall()
        
        if not rows: return 0.0
        
        # --- LOGIKA WYBORU POZYCJI (SNAJPER) ---
        # To jest ten fragment, który naprawia błąd zamykania "na ślepo"
        poz = None
        
        # 1. Jeśli podano typ (np. 'godzinowa'), szukamy idealnego dopasowania
        if typ_strategii:
            for r in rows:
                if r[2] == typ_strategii: # r[2] to kolumna typ_strategii
                    poz = r
                    break
        
        # 2. Jeśli nie znaleziono lub nie podano typu, szukamy po źródle (logika Usera)
        if not poz and zrodlo:
            for r in rows:
                if zrodlo == "SKANER" and r[6] == "SKANER": poz = r; break
                if zrodlo != "SKANER" and r[6] != "SKANER": poz = r; break
        
        # 3. Fallback (pierwsza z brzegu - ostateczność)
        if not poz: poz = rows[0] 
        
        # Rozpakuj dane z SQL
        unikalne_id = poz[0]
        typ_strat_db = poz[2]
        cena_wej = poz[3]
        ilosc = poz[4]
        
        wartosc_wyjscia = ilosc * cena_wyjscia
        wartosc_wejscia = ilosc * cena_wej
        zysk_netto = wartosc_wyjscia - wartosc_wejscia
        zysk_proc = ((cena_wyjscia - cena_wej) / cena_wej) * 100
        
        # --- TRANSAKCJA ---
        # 1. Usuń pozycję PO UNIKALNYM ID (To jest klucz do naprawy!)
        db.cursor.execute("DELETE FROM aktywne_pozycje WHERE unikalne_id=?", (unikalne_id,))
        
        # 2. Dodaj kasę do salda
        db.aktualizuj_saldo(wartosc_wyjscia)
        
        # 3. Zapisz w historii
        db.zapisz_historie_transakcji(symbol, typ_strat_db, zysk_netto, zysk_proc, "Sprzedaż")
        
        # 4. Nauka AI (z Twojego kodu)
        if zrodlo != "SKANER":
            db.aktualizuj_strategie_mozgu(symbol, typ_strat_db, zysk_proc, "ZAKONCZONA")
            print(f"   💾 [SQL] Zaktualizowano inteligencję dla {symbol} ({zysk_proc:.2f}%)")

        # Wymuszenie zapisu (dla WAL)
        db.conn.commit()

        return zysk_netto

    except Exception as e:
        print(f"⚠️ Błąd SQL przy sprzedaży: {e}")
        return 0.0

