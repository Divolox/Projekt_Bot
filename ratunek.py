import sqlite3

# Nazwa pliku bazy
DB_NAME = "baza_bota.db"

def zabij_zombie():
    print("🚑 URUCHAMIAM PROCEDURĘ RATUNKOWĄ...")
    
    try:
        conn = sqlite3.connect(DB_NAME, timeout=60.0)
        cursor = conn.cursor()
        
        # 1. Sprawdź co tam siedzi
        cursor.execute("SELECT unikalne_id, symbol, typ_strategii FROM aktywne_pozycje")
        trupy = cursor.fetchall()
        
        if not trupy:
            print("✅ Baza jest pusta. Brak zombie.")
            return

        print(f"⚠️ Znaleziono {len(trupy)} aktywnych pozycji (ZOMBIE):")
        for t in trupy:
            print(f"   💀 {t[0]} ({t[1]} - {t[2]})")

        # 2. Usuwanie siłowe
        decyzja = input("\nCzy usunąć je wszystkie SIŁOWO? (tak/nie): ")
        
        if decyzja.lower() == 'tak':
            cursor.execute("DELETE FROM aktywne_pozycje")
            conn.commit()
            print("\n💥 JEBUT. Wszystkie pozycje usunięte z bazy danych.")
            print("   (Twoje saldo w 'portfel' zostało bez zmian, usunięto tylko wiszące transakcje)")
        else:
            print("Anulowano.")

        conn.close()

    except Exception as e:
        print(f"❌ Błąd: {e}")

if __name__ == "__main__":
    zabij_zombie()

