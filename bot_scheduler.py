import json
import os
import time
import datetime
import portfel_manager as pm

# ==========================================
# ⚙️ SCHEDULER (MULTI-SLOT)
# ==========================================
PLIK_MOZGU = "mozg.json"                
PLIK_RYNKU = "rynek.json"               
STRATEGIE_DB = "strategie_bota.json"    

# LIMIT CAŁKOWITY (Bezpiecznik)
MAX_POZYCJI_MAIN = 3  # Zwiększamy lekko, skoro chcesz mieć np. BTC 1h + BTC 1w

def wczytaj_json(plik):
    if not os.path.exists(plik): return {}
    try:
        with open(plik, "r") as f: return json.load(f)
    except Exception as e:
        print(f"⚠️ Błąd odczytu {plik}: {e}")
        return {}

def zapisz_json(plik, dane):
    try:
        with open(plik, "w") as f: json.dump(dane, f, indent=4)
    except Exception as e:
        print(f"⚠️ Błąd zapisu {plik}: {e}")

def pobierz_cene_z_rynku(rynek_data, symbol):
    """Pancerna funkcja do wyciągania ceny."""
    symbol_short = symbol.replace("USDT", "") 
    symbol_long = symbol_short + "USDT"       

    prices_list = rynek_data.get("prices", [])
    if isinstance(prices_list, list):
        for item in prices_list:
            if item.get("symbol") == symbol_long or item.get("symbol") == symbol_short:
                return float(item.get("current_price", 0.0))

    data_section = rynek_data.get("data", rynek_data)
    coin_data = data_section.get(symbol_short, data_section.get(symbol_long))
    
    if coin_data and "1h" in coin_data and len(coin_data["1h"]) > 0:
        return float(coin_data["1h"][-1].get("c", 0.0))

    return 0.0

def wykonaj_zlecenia():
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 🤖 SCHEDULER: Rozpoczynam cykl...")

    decyzja = wczytaj_json(PLIK_MOZGU)
    rynek = wczytaj_json(PLIK_RYNKU)
    aktywne_pozycje = wczytaj_json(STRATEGIE_DB)

    # 1. SPRAWDZENIE LIMITU SLOTÓW
    liczba_aktywnych = len(aktywne_pozycje)
    if liczba_aktywnych >= MAX_POZYCJI_MAIN:
        print(f"   ⛔ PEŁNY PORTFEL ({liczba_aktywnych}/{MAX_POZYCJI_MAIN}). Nie otwieram nowych pozycji.")
        return 

    timestamp_decyzji = decyzja.get("timestamp", 0)
    akcja = decyzja.get("akcja", "").upper()
    symbol = decyzja.get("symbol")
    typ_strategii = decyzja.get("typ_strategii", "STANDARD")

    # Konwersja czasu
    if isinstance(timestamp_decyzji, str):
        try:
            dt_obj = datetime.datetime.fromisoformat(timestamp_decyzji)
            timestamp_decyzji = dt_obj.timestamp()
        except ValueError:
            timestamp_decyzji = 0

    if time.time() - timestamp_decyzji > 1800:
        print("   (Decyzja mózgu jest stara - pomijam)")
        return

    if akcja == "KUP" and symbol:
        # --- KLUCZOWA ZMIANA: UNIKALNY ID POZYCJI ---
        # Tworzymy ID z Symbolu I Typu strategii (np. BTCUSDT_godzinowa)
        # To pozwala mieć BTC tygodniowe i BTC godzinowe osobno.
        unikalne_id = f"{symbol}_{typ_strategii}"
        
        if unikalne_id in aktywne_pozycje:
            print(f"⚠️ Masz już otwartą pozycję {symbol} na interwale {typ_strategii}. Pomijam.")
            return
        # --------------------------------------------

        aktualna_cena = pobierz_cene_z_rynku(rynek, symbol)

        if aktualna_cena <= 0:
            print(f"⛔ Błąd krytyczny: Cena dla {symbol} wynosi 0.0!")
            return

        print(f"   💡 Wykryto sygnał KUP: {symbol} [{typ_strategii}]. Cena: {aktualna_cena}")

        sukces, ilosc_kupiona, koszt_usdt = pm.pobierz_srodki(
            symbol, 
            aktualna_cena, 
            procent_kapitalu=0.10, 
            zrodlo="MAIN_BOT"
        )

        if sukces:
            print(f"   ✅ ZAKUP UDANY! Zainwestowano: {koszt_usdt:.2f} USDT")
            
            nowa_strategia = {
                "symbol": symbol,
                "typ": typ_strategii,
                "status": "OTWARTA",
                "cena_wejscia": aktualna_cena,
                "czas_wejscia": time.time(),
                "ilosc": ilosc_kupiona,
                "max_zysk": 0.0, 
                "analiza_ai": decyzja.get("uzasadnienie", "Brak danych")
            }

            # Zapisujemy pod unikalnym ID
            aktywne_pozycje[unikalne_id] = nowa_strategia
            zapisz_json(STRATEGIE_DB, aktywne_pozycje)
            print(f"   💾 Zapisano pozycję {unikalne_id} w {STRATEGIE_DB}")

            decyzja["akcja"] = "ZREALIZOWANO"
            decyzja["timestamp"] = time.time() 
            zapisz_json(PLIK_MOZGU, decyzja)
        else:
            print(f"   ⛔ BRAK ŚRODKÓW W PORTFELU na zakup {symbol}!")

    elif akcja == "ZREALIZOWANO":
        print("   (Ostatnia decyzja została już zrealizowana)")
    else:
        print("   (Brak nowych sygnałów zakupu)")

if __name__ == "__main__":
    wykonaj_zlecenia()