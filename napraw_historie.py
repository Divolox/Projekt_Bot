from database_handler import DatabaseHandler


def napraw_baze():
    db = DatabaseHandler()
    cursor = db.cursor

    print("🔧 Sprawdzam tabelę 'historia_transakcji'...")

    try:
        cursor.execute("SELECT count(*) FROM historia_transakcji")
        count = cursor.fetchone()[0]
        print(f"✅ Tabela istnieje. Liczba wpisów: {count}")
    except Exception:
        print("⚠️ Tabela NIE istnieje. Tworzę ją...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historia_transakcji (
                id SERIAL PRIMARY KEY,
                symbol TEXT,
                typ_strategii TEXT,
                cena_wejscia REAL,
                cena_wyjscia REAL,
                ilosc REAL,
                zysk_usd REAL,
                zysk_proc REAL,
                czas_wejscia REAL,
                czas_wyjscia REAL,
                powod_wyjscia TEXT
            )
        """)
        db.conn.commit()
        print("✅ Utworzono tabelę 'historia_transakcji'.")

    cursor.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'historia_transakcji'
        ORDER BY ordinal_position
    """)
    kolumny = [row[0] for row in cursor.fetchall()]

    wymagane = ["symbol", "zysk_proc", "czas_wyjscia"]
    brakujace = [k for k in wymagane if k not in kolumny]

    if brakujace:
        print(f"❌ KRYTYCZNE: Brakuje kolumn w bazie: {brakujace}")
        print("🔧 Dodaję brakujące kolumny...")
        for k in brakujace:
            try:
                typ = "REAL" if k != "powod_wyjscia" else "TEXT"
                cursor.execute(f"ALTER TABLE historia_transakcji ADD COLUMN {k} {typ}")
                print(f"   -> Dodano kolumnę: {k}")
            except Exception as e:
                print(f"   -> Błąd przy dodawaniu {k}: {e}")
        db.conn.commit()
    else:
        print("✅ Wszystkie wymagane kolumny są na miejscu.")

    try:
        cursor.execute("SELECT count(*) FROM historia_transakcji WHERE zysk_proc < 0")
        stratne = cursor.fetchone()[0]
        print(f"📊 Statystyka: Masz {stratne} stratnych transakcji w historii (potencjalne bany).")
    except Exception as e:
        print(f"❌ Błąd testu zapytania: {e}")

    db.close()
    print("🏁 Naprawa zakończona.")


if __name__ == "__main__":
    napraw_baze()

