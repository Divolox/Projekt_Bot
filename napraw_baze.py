import json
import os

# Pliki do wyczyszczenia
DB_FILE = 'strategie_bota.json'   # Tu są aktywne pozycje (blokady)
CANDIDATES_FILE = 'strategie.json' # Tu są kandydaci (to co wkleiłeś)

def resetuj_wszystko():
    print("="*40)
    print("🧹 ROZPOCZYNAM TOTALNY RESET POZYCJI")
    print("="*40)

    # 1. CZYSZCZENIE AKTYWNYCH POZYCJI (Baza)
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, 'r') as f:
                dane = json.load(f)
            
            zmienione = 0
            # Lecimy po wszystkim jak leci
            if isinstance(dane, dict):
                for klucz, pozycja in dane.items():
                    # Jeśli status nie wskazuje na zamknięcie, zamykamy siłowo
                    status_akt = pozycja.get('status', '').lower()
                    if 'zamknieta' not in status_akt and 'sprzedane' not in status_akt:
                        pozycja['status'] = 'zamknieta_reset_mobilny'
                        pozycja['wynik_koncowy'] = 'RESET RĘCZNY'
                        print(f"   ❌ Zamykam siłowo: {klucz} (Status był: {status_akt})")
                        zmienione += 1
            
            # Zapisujemy
            with open(DB_FILE, 'w') as f:
                json.dump(dane, f, indent=4)
            print(f"   ✅ Zaktualizowano bazę. Zamknięto {zmienione} pozycji.")
            
        except Exception as e:
            print(f"   ⚠️ Błąd bazy: {e}")
    else:
        print(f"   ℹ️ Plik {DB_FILE} nie istnieje (to dobrze, brak blokad).")

    # 2. CZYSZCZENIE KANDYDATÓW (To co wkleiłeś)
    # Czyścimy to, żeby bot nie kupił starych sygnałów po starcie
    try:
        with open(CANDIDATES_FILE, 'w') as f:
            json.dump([], f)
        print(f"   ✅ Wyczyszczono plik kandydatów ({CANDIDATES_FILE}).")
    except Exception as e:
        print(f"   ⚠️ Błąd czyszczenia kandydatów: {e}")

    print("-" * 40)
    print("🚀 GOTOWE! Twój bot ma teraz 0/3 zajętych slotów.")
    print("   Możesz bezpiecznie odpalać 'orchestrator.py'.")
    print("=" * 40)

if __name__ == "__main__":
    resetuj_wszystko()