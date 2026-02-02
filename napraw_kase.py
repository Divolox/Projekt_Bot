import sqlite3
import os

DB_NAME = "baza_bota.db"

def napraw_saldo():
    print("="*40)
    print("🚑 NARZĘDZIE DO RĘCZNEJ KOREKTY SALDA")
    print("="*40)

    if not os.path.exists(DB_NAME):
        print(f"❌ Nie znaleziono pliku {DB_NAME}!")
        return

    try:
        # Łączymy się z bazą
        conn = sqlite3.connect(DB_NAME, timeout=60.0)
        cursor = conn.cursor()

        # 1. POBIERZ OBECNE SALDO
        cursor.execute("SELECT saldo_gotowka FROM portfel WHERE id=1")
        wynik = cursor.fetchone()
        
        if not wynik:
            print("⚠️ Brak portfela w bazie! Tworzę domyślny...")
            cursor.execute("INSERT INTO portfel (id, saldo_gotowka) VALUES (1, 1000.0)")
            conn.commit()
            obecne_saldo = 1000.0
        else:
            obecne_saldo = wynik[0]

        print(f"💰 Obecne saldo w bazie: {obecne_saldo:.2f} USDT")
        print("-" * 40)

        # 2. ZAPYTAJ O NOWE SALDO
        try:
            nowa_kwota_str = input("👉 Wpisz poprawne saldo (np. 1350.50): ")
            nowa_kwota = float(nowa_kwota_str.replace(",", "."))
        except ValueError:
            print("❌ To nie jest poprawna liczba!")
            return

        # 3. ZAPISZ W BAZIE
        cursor.execute("UPDATE portfel SET saldo_gotowka = ? WHERE id=1", (nowa_kwota,))
        conn.commit()
        
        print("✅ SUKCES! Saldo zaktualizowane.")
        print(f"   Nowy stan konta: {nowa_kwota:.2f} USDT")

        # 4. OPCJA: CZYSZCZENIE ZOMBIE
        print("\n💀 Czy chcesz przy okazji wyczyścić zawieszone pozycje (zombie)?")
        print("   (Wpisz 'tak', jeśli bot widzi pozycje, których już nie powinno być)")
        decyzja = input("   Twój wybór (tak/nie): ").lower()

        if decyzja == 'tak':
            cursor.execute("DELETE FROM aktywne_pozycje")
            conn.commit()
            print("💥 Wyczyszczono wszystkie aktywne pozycje z bazy.")
        
        conn.close()

    except Exception as e:
        print(f"❌ Wystąpił błąd: {e}")

if __name__ == "__main__":
    napraw_saldo()

