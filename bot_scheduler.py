import json
import os
import time
import datetime
import sys

# Dodajemy ścieżkę
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    import portfel_manager as pm
    from database_handler import DatabaseHandler # Baza
except ImportError:
    print("❌ SCHEDULER: Brak modułów bazy/portfela.")
    sys.exit()

PLIK_MOZGU = "mozg.json"
PLIK_RYNKU = "rynek.json"

# LIMIT CAŁKOWITY (Bezpiecznik dla Bota Głównego)
MAX_POZYCJI_MAIN = 3
db = DatabaseHandler()

def wczytaj_json(plik):
    if not os.path.exists(plik): return {}
    try:
        with open(plik, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def pobierz_cene_z_rynku(rynek_data, symbol):
    symbol_short = symbol.replace("USDT", "")
    symbol_long = symbol_short + "USDT"

    prices_list = rynek_data.get("prices", [])
    if isinstance(prices_list, list):
        for item in prices_list:
            if item.get("symbol") == symbol_long or item.get("symbol") == symbol_short:
                return float(item.get("current_price", 0.0))

    data_section = rynek_data.get("data", rynek_data)
    coin_data = data_section.get(symbol_short, data_section.get(symbol_long))
    if coin_data and isinstance(coin_data, dict) and "1h" in coin_data and len(coin_data["1h"]) > 0:
        return float(coin_data["1h"][-1].get("c", 0.0))
    if isinstance(coin_data, dict) and "lastPrice" in coin_data:
        return float(coin_data["lastPrice"])
    return 0.0

def wykonaj_zlecenia():
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 🤖 SCHEDULER: Weryfikacja rozkazów...")

    decyzja = wczytaj_json(PLIK_MOZGU)
    if not decyzja:
        print("   (Brak nowych rozkazów)")
        return

    rynek = wczytaj_json(PLIK_RYNKU)

    # 1. SPRAWDZENIE LIMITU SLOTÓW W SQL
    # Liczymy tylko pozycje Bota Głównego (zrodlo != 'SKANER')
    try:
        db.cursor.execute("SELECT count(*) FROM aktywne_pozycje WHERE zrodlo != 'SKANER'")
        liczba_aktywnych = db.cursor.fetchone()[0]
    except Exception as e:
        print(f"⚠️ Błąd SQL: {e}")
        return

    timestamp_decyzji = decyzja.get("timestamp", 0)
    akcja = decyzja.get("akcja", "").upper()
    symbol = decyzja.get("symbol")
    typ_strategii = decyzja.get("typ_strategii", "STANDARD")

    if isinstance(timestamp_decyzji, str):
        try:
            dt_obj = datetime.datetime.fromisoformat(timestamp_decyzji)
            timestamp_decyzji = dt_obj.timestamp()
        except ValueError: timestamp_decyzji = 0

    if time.time() - timestamp_decyzji > 1800:
        print("   (Decyzja stara >30min - pomijam)")
        if os.path.exists(PLIK_MOZGU): os.remove(PLIK_MOZGU)
        return

    if akcja == "KUP" and symbol:
        if liczba_aktywnych >= MAX_POZYCJI_MAIN:
            print(f"   ⛔ PEŁNY PORTFEL ({liczba_aktywnych}/{MAX_POZYCJI_MAIN}).")
            if os.path.exists(PLIK_MOZGU): os.remove(PLIK_MOZGU)
            return

        unikalne_id = f"{symbol}_{typ_strategii}"
        
        # Sprawdzamy w bazie czy już mamy tę pozycję
        db.cursor.execute("SELECT count(*) FROM aktywne_pozycje WHERE unikalne_id=?", (unikalne_id,))
        if db.cursor.fetchone()[0] > 0:
            print(f"⚠️ Pozycja {unikalne_id} już otwarta.")
            if os.path.exists(PLIK_MOZGU): os.remove(PLIK_MOZGU)
            return

        aktualna_cena = pobierz_cene_z_rynku(rynek, symbol)
        if aktualna_cena <= 0:
            print(f"⛔ Błąd ceny dla {symbol}.")
            return

        print(f"   💡 Wykryto sygnał KUP: {symbol} [{typ_strategii}]")

        # Portfel Manager sam doda wpis do SQL
        sukces, ilosc, koszt = pm.pobierz_srodki(
            symbol,
            aktualna_cena,
            0.10,
            "MAIN_BOT",
            typ_strategii
        )

        if sukces:
            print(f"   ✅ ZAKUP UDANY! Zainwestowano: {koszt:.2f} USDT")
            if os.path.exists(PLIK_MOZGU): os.remove(PLIK_MOZGU)
        else:
            print(f"   ⛔ ZAKUP ODRZUCONY (Błąd SQL lub brak środków).")

    elif akcja == "ZREALIZOWANO":
        if os.path.exists(PLIK_MOZGU): os.remove(PLIK_MOZGU)
    
    elif akcja == "CZEKAJ":
        print(f"   💤 Mózg: Czekaj. ({decyzja.get('powod','')})")
        if os.path.exists(PLIK_MOZGU): os.remove(PLIK_MOZGU)

if __name__ == "__main__":
    wykonaj_zlecenia()