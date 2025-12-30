import json
import os
import time
import datetime
# Importujemy nasz bank (musi być w tym samym folderze)
import portfel_manager as pm

# ==========================================
# ⚙️ KONFIGURACJA PLIKÓW
# ==========================================
PLIK_MOZGU = "mozg.json"                # Decyzje AI
PLIK_RYNKU = "rynek.json"               # Aktualne ceny (z Obserwatora)
PLIK_STRATEGII_INPUT = "strategie.json" # Nowe pomysły (Skrzynka odbiorcza)
STRATEGIE_DB = "strategie_bota.json"    # Aktywne pozycje (Księga główna)

def wczytaj_json(plik):
    """Pomocnicza funkcja do bezpiecznego wczytywania JSON"""
    if not os.path.exists(plik):
        return {}
    try:
        with open(plik, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Błąd odczytu {plik}: {e}")
        return {}

def zapisz_json(plik, dane):
    """Pomocnicza funkcja do zapisu JSON"""
    try:
        with open(plik, "w") as f:
            json.dump(dane, f, indent=4)
    except Exception as e:
        print(f"⚠️ Błąd zapisu {plik}: {e}")

def wykonaj_zlecenia():
    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] 🤖 SCHEDULER: Rozpoczynam cykl...")

    # 1. Wczytujemy dane
    decyzja = wczytaj_json(PLIK_MOZGU)
    rynek = wczytaj_json(PLIK_RYNKU)
    aktywne_pozycje = wczytaj_json(STRATEGIE_DB)

    # 2. Sprawdzamy, czy Mózg dał sygnał KUP
    timestamp_decyzji = decyzja.get("timestamp", 0)
    akcja = decyzja.get("akcja", "").upper()
    symbol = decyzja.get("symbol")

    # Walidacja czasu (czy sygnał nie jest przestarzały > 30 min)
    if time.time() - timestamp_decyzji > 1800:
        print("   (Decyzja mózgu jest stara - pomijam)")
        return

    # 3. Logika otwierania pozycji
    if akcja == "KUP" and symbol:
        # Sprawdzamy, czy już nie mamy tego coina w aktywnych
        if symbol in aktywne_pozycje:
            print(f"⚠️ {symbol} jest już w aktywnych strategiach. Pomijam dublowanie.")
            return

        # Pobieramy AKTUALNĄ cenę z rynku (a nie z mózgu!)
        # Rynek.json ma strukturę { "BTCUSDT": { "price": 95000, ... } }
        dane_rynkowe = rynek.get(symbol, {})
        aktualna_cena = float(dane_rynkowe.get("price", 0.0))

        if aktualna_cena <= 0:
            print(f"⛔ Błąd: Brak ceny dla {symbol} w {PLIK_RYNKU}!")
            return

        print(f"   💡 Wykryto sygnał KUP dla {symbol}. Cena rynkowa: {aktualna_cena}")

        # --- TUTAJ WCHODZI PORTFEL MANAGER ---
        # Próbujemy pobrać środki z wirtualnego portfela
        # Źródło oznaczamy jako 'MAIN_BOT', żeby Evaluator wiedział, że to jego działka
        sukces, ilosc_kupiona, koszt_usdt = pm.pobierz_srodki(
            symbol, 
            aktualna_cena, 
            procent_kapitalu=0.10, 
            zrodlo="MAIN_BOT"
        )

        if sukces:
            print(f"   ✅ ZAKUP UDANY! Zainwestowano: {koszt_usdt:.2f} USDT")
            
            # Tworzymy wpis do bazy strategii (Tak jak w Twoim oryginale)
            nowa_strategia = {
                "symbol": symbol,
                "typ": decyzja.get("strategia", "STANDARD"), # Np. wybicie, korekta
                "status": "OTWARTA",
                "cena_wejscia": aktualna_cena,
                "czas_wejscia": time.time(),
                "ilosc": ilosc_kupiona,
                "max_zysk": 0.0, # Do śledzenia trailng stopa
                "analiza_ai": decyzja.get("analiza", "Brak danych")
            }

            # Dodajemy do bazy aktywnych (strategie_bota.json)
            aktywne_pozycje[symbol] = nowa_strategia
            zapisz_json(STRATEGIE_DB, aktywne_pozycje)
            print(f"   💾 Zapisano pozycję w {STRATEGIE_DB}")

            # Czyścimy mózg (zmieniamy status na ZREALIZOWANO), żeby nie kupił znowu
            decyzja["akcja"] = "ZREALIZOWANO"
            decyzja["timestamp"] = time.time() # Odświeżamy czas, żeby wiedzieć kiedy zrealizowano
            zapisz_json(PLIK_MOZGU, decyzja)

        else:
            print(f"   ⛔ BRAK ŚRODKÓW W PORTFELU na zakup {symbol}!")

    elif akcja == "ZREALIZOWANO":
        print("   (Ostatnia decyzja została już zrealizowana)")
    else:
        print("   (Brak nowych sygnałów zakupu)")

if __name__ == "__main__":
    wykonaj_zlecenia()