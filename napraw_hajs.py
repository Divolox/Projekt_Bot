from database_handler import DatabaseHandler


def main():
    db = DatabaseHandler()
    try:
        db.cursor.execute("SELECT saldo_gotowka FROM portfel WHERE id=1")
        wynik = db.cursor.fetchone()
        if not wynik:
            print("❌ Tabela portfel jest pusta!")
            return
        obecne = wynik[0]
        print(f"💰 Obecne saldo gotówki w bazie: {obecne:.2f} USDT")

        db.cursor.execute("SELECT symbol, ilosc, cena_wejscia FROM aktywne_pozycje")
        pozycje = db.cursor.fetchall()
        
        print(f"\n📦 Aktywne pozycje w bazie ({len(pozycje)}):")
        for p in pozycje:
            sym = p[0]
            ilosc = p[1]
            cena = p[2]
            wartosc = ilosc * cena
            print(f"   - {sym}: {ilosc:.4f} szt. (Kupione za ~{wartosc:.2f} USDT)")

        print("-" * 40)
        print("💡 Jeśli zniknęło Ci 100$, dodaj je do obecnego salda.")
        nowe_saldo_str = input(f"Podaj NOWE poprawne saldo gotówki (np. {obecne + 100:.2f}): ")
        
        nowe_float = float(nowe_saldo_str.replace(",", "."))
        db.cursor.execute("UPDATE portfel SET saldo_gotowka = %s WHERE id=1", (nowe_float,))
        db.conn.commit()
        print(f"✅ SUKCES! Zaktualizowano saldo na: {nowe_float:.2f} USDT")
        
    except Exception as e:
        print(f"❌ Wystąpił błąd: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    main()