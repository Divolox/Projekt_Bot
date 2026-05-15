from database_handler import DatabaseHandler


def zabij_zombie():
    print("🚑 URUCHAMIAM PROCEDURĘ RATUNKOWĄ...")
    db = DatabaseHandler()
    try:
        db.cursor.execute("SELECT unikalne_id, symbol, typ_strategii FROM aktywne_pozycje")
        trupy = db.cursor.fetchall()

        if not trupy:
            print("✅ Baza jest pusta. Brak zombie.")
            return

        print(f"⚠️ Znaleziono {len(trupy)} aktywnych pozycji (ZOMBIE):")
        for t in trupy:
            print(f"   💀 {t[0]} ({t[1]} - {t[2]})")

        decyzja = input("\nCzy usunąć je wszystkie SIŁOWO? (tak/nie): ")
        if decyzja.lower() == 'tak':
            db.cursor.execute("DELETE FROM aktywne_pozycje")
            db.conn.commit()
            print("\n💥 JEBUT. Wszystkie pozycje usunięte z bazy danych.")
            print("   (Twoje saldo w 'portfel' zostało bez zmian, usunięto tylko wiszące transakcje)")
        else:
            print("Anulowano.")

    except Exception as e:
        print(f"❌ Błąd: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    zabij_zombie()

