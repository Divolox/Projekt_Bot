import sqlite3
import os

DB_NAME = "baza_bota.db"

def main():
    if not os.path.exists(DB_NAME):
        print("❌ Brak bazy danych!")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Sprawdź obecne saldo
    try:
        cursor.execute("SELECT saldo_gotowka FROM portfel WHERE id=1")
        wynik = cursor.fetchone()
        if not wynik:
            print("❌ Tabela portfel jest pusta!")
            return
        obecne = wynik[0]
        print(f"💰 Obecne saldo gotówki w bazie: {obecne:.2f} USDT")

        # Sprawdź aktywne pozycje
        # POPRAWKA: Pobieramy cena_wejscia zamiast nieistniejącej wartosc_wejscia
        cursor.execute("SELECT symbol, ilosc, cena_wejscia FROM aktywne_pozycje")
        pozycje = cursor.fetchall()
        
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
        cursor.execute("UPDATE portfel SET saldo_gotowka = ? WHERE id=1", (nowe_float,))
        conn.commit()
        print(f"✅ SUKCES! Zaktualizowano saldo na: {nowe_float:.2f} USDT")
        
    except Exception as e:
        print(f"❌ Wystąpił błąd: {e}")
    
    conn.close()

if __name__ == "__main__":
    main()