import json
import os
from datetime import datetime
from pathlib import Path

PLIK = "strategie_bota.json"

def wczytaj_strategie_bota():
    """Wczytuje surowe dane (Słownik)"""
    if not os.path.exists(PLIK):
        return {}
    try:
        with open(PLIK, "r", encoding="utf-8") as f:
            dane = json.load(f)
            # Jeśli przypadkiem plik jest pusty lub błędny, zwróć pusty słownik
            if not isinstance(dane, dict):
                return {}
            return dane
    except:
        return {}

def zapisz_strategie_bota(dane):
    """Zapisuje dane (Słownik)"""
    try:
        with open(PLIK, "w", encoding="utf-8") as f:
            json.dump(dane, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"⚠️ Błąd zapisu strategii: {e}")

# --- TA FUNKCJA JEST WYMAGANA PRZEZ PORTFEL_MANAGER ---
def aktualizuj_status_strategii(symbol, nowy_status, wynik_str=""):
    """
    Szuka w słowniku strategii, która ma dany symbol i jest OTWARTA.
    Zmienia jej status na ZAKONCZONA (lub inny podany).
    """
    strategie = wczytaj_strategie_bota() # To teraz zwraca słownik {}
    zmiana = False

    # Iterujemy po kluczach (np. "BTC_jednodniowa") i wartościach
    for klucz_id, dane in strategie.items():
        
        biezacy_symbol = dane.get("symbol")
        biezacy_status = dane.get("status")

        # Sprawdzamy czy to ten coin i czy jest aktywny
        # (Obsługujemy też 'oczekuje' i 'AKTYWNA' dla pewności)
        if biezacy_symbol == symbol and biezacy_status in ["OTWARTA", "AKTYWNA", "oczekuje"]:
            
            # Zmiana danych w pamięci
            strategie[klucz_id]["status"] = nowy_status
            strategie[klucz_id]["czas_zamkniecia"] = datetime.now().timestamp()
            strategie[klucz_id]["powod_zamkniecia"] = "Sprzedaż przez Portfel Managera"

            # Dodanie wyniku dla AI
            if "ocena" not in strategie[klucz_id]:
                strategie[klucz_id]["ocena"] = {}
            
            strategie[klucz_id]["ocena"]["wynik"] = wynik_str
            strategie[klucz_id]["ocena"]["czas_oceny"] = datetime.now().isoformat()

            print(f"💾 [DATA_STORAGE] Zaktualizowano {klucz_id}: {nowy_status} ({wynik_str})")
            zmiana = True

    if zmiana:
        zapisz_strategie_bota(strategie)
    else:
        # Opcjonalny log debugowania, jeśli nic nie znalazł (można wyłączyć)
        # print(f"ℹ️ Nie znaleziono aktywnej strategii dla {symbol} w pliku {PLIK}")
        pass

