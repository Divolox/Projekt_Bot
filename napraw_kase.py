from database_handler import DatabaseHandler


def napraw_saldo():
    print("="*40)
    print("🚑 NARZĘDZIE DO RĘCZNEJ KOREKTY SALDA")
    print("="*40)

    db = DatabaseHandler()
    try:
        db.cursor.execute("SELECT saldo_gotowka FROM portfel WHERE id=1")
        wynik = db.cursor.fetchone()
        
        if not wynik:
            print("⚠️ Brak portfela w bazie! Tworzę domyślny...")
            db.cursor.execute("INSERT INTO portfel (id, saldo_gotowka) VALUES (1, 1000.0)")
            db.conn.commit()
            obecne_saldo = 1000.0
        else:
            obecne_saldo = wynik[0]

        print(f"💰 Obecne saldo w bazie: {obecne_saldo:.2f} USDT")
        print("-" * 40)

        try:
            nowa_kwota_str = input("👉 Wpisz poprawne saldo (np. 1350.50): ")
            nowa_kwota = float(nowa_kwota_str.replace(",", "."))
        except ValueError:
            print("❌ To nie jest poprawna liczba!")
            return

        db.cursor.execute("UPDATE portfel SET saldo_gotowka = %s WHERE id=1", (nowa_kwota,))
        db.conn.commit()
        
        print("✅ SUKCES! Saldo zaktualizowane.")
        print(f"   Nowy stan konta: {nowa_kwota:.2f} USDT")

        print("\n💀 Czy chcesz przy okazji wyczyścić zawieszone pozycje (zombie)?")
        print("   (Wpisz 'tak', jeśli bot widzi pozycje, których już nie powinno być)")
        decyzja = input("   Twój wybór (tak/nie): ").lower()

        if decyzja == 'tak':
            db.cursor.execute("DELETE FROM aktywne_pozycje")
            db.conn.commit()
            print("💥 Wyczyszczono wszystkie aktywne pozycje z bazy.")
    except Exception as e:
        print(f"❌ Wystąpił błąd: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    napraw_saldo()

