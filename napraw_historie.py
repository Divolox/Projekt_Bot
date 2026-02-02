import sqlite3
import os

DB_NAME = "baza_bota.db"

def napraw_baze():
    if not os.path.exists(DB_NAME):
        print(f"❌ Błąd: Nie widzę pliku {DB_NAME}. Upewnij się, że jesteś w folderze bot_sql!")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    print("🔧 Sprawdzam tabelę 'historia_transakcji'...")

    # 1. Sprawdź czy tabela istnieje
    try:
        cursor.execute("SELECT count(*) FROM historia_transakcji")
        count = cursor.fetchone()[0]
        print(f"✅ Tabela istnieje. Liczba wpisów: {count}")
    except sqlite3.OperationalError:
        print("⚠️ Tabela NIE istnieje. Tworzę ją...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS historia_transakcji (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        conn.commit()
        print("✅ Utworzono tabelę 'historia_transakcji'.")

    # 2. Sprawdź czy są odpowiednie kolumny (ważne dla Czarnej Listy!)
    # Potrzebujemy: symbol, zysk_proc, czas_wyjscia
    cursor.execute("PRAGMA table_info(historia_transakcji)")
    kolumny = [row[1] for row in cursor.fetchall()]
    
    wymagane = ["symbol", "zysk_proc", "czas_wyjscia"]
    brakujace = [k for k in wymagane if k not in kolumny]

    if brakujace:
        print(f"❌ KRYTYCZNE: Brakuje kolumn w bazie: {brakujace}")
        print("🔧 Dodaję brakujące kolumny...")
        for k in brakujace:
            try:
                # Domyślny typ REAL dla liczb, TEXT dla innych (tu upraszczam)
                typ = "REAL"
                cursor.execute(f"ALTER TABLE historia_transakcji ADD COLUMN {k} {typ}")
                print(f"   -> Dodano kolumnę: {k}")
            except Exception as e:
                print(f"   -> Błąd przy dodawaniu {k}: {e}")
        conn.commit()
    else:
        print("✅ Wszystkie wymagane kolumny są na miejscu.")

    # 3. Testowy odczyt (Symulacja Czarnej Listy)
    try:
        cursor.execute("SELECT count(*) FROM historia_transakcji WHERE zysk_proc < 0")
        stratne = cursor.fetchone()[0]
        print(f"📊 Statystyka: Masz {stratne} stratnych transakcji w historii (potencjalne bany).")
    except Exception as e:
        print(f"❌ Błąd testu zapytania: {e}")

    conn.close()
    print("🏁 Naprawa zakończona.")

if __name__ == "__main__":
    napraw_baze()

