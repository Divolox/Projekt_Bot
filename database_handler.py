import sqlite3
import time
import os

# Nazwa pliku bazy danych
DB_NAME = "baza_bota.db"

class DatabaseHandler:
    def __init__(self, db_name=DB_NAME):
        """Łączy się z bazą."""
        self.db_name = db_name
        # ZMIANA 1: Timeout 60s + Tryb WAL (Kluczowe dla stabilności)
        self.conn = sqlite3.connect(self.db_name, check_same_thread=False, timeout=60.0)
        self.conn.execute('PRAGMA journal_mode=WAL;') # To naprawia "database is locked"
        self.cursor = self.conn.cursor()
        self._inicjalizuj_tabele()

    def _inicjalizuj_tabele(self):
        # 1. PORTFEL
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfel (
                id INTEGER PRIMARY KEY,
                saldo_gotowka REAL DEFAULT 1000.0,
                zablokowany BOOLEAN DEFAULT 0
            )
        ''')
        # Sprawdzenie czy rekord istnieje, jeśli nie - wstawienie
        self.cursor.execute('SELECT count(*) FROM portfel WHERE id=1')
        if self.cursor.fetchone()[0] == 0:
            self.cursor.execute('INSERT INTO portfel (id, saldo_gotowka) VALUES (1, 1000.0)')
            self.conn.commit()

        # 2. AKTYWNE POZYCJE (Z obsługą Max Zysk dla Twoich strategii)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS aktywne_pozycje (
                unikalne_id TEXT PRIMARY KEY,
                symbol TEXT,
                typ_strategii TEXT,
                cena_wejscia REAL,
                ilosc REAL,
                czas_wejscia REAL,
                zrodlo TEXT,
                stop_loss REAL,
                analiza_ai TEXT,
                max_zysk REAL DEFAULT 0.0  -- Niezbędne dla Twojego Ewaluatora
            )
        ''')

        # 3. HISTORIA TRANSAKCJI
        # ZMIANA 2: Dodano kolumnę czas_wyjscia (wymagana przez Skaner)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS historia_transakcji (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                typ_strategii TEXT,
                zysk_usdt REAL,
                zysk_proc REAL,
                czas_zamkniecia REAL,
                powod TEXT,
                czas_wyjscia REAL
            )
        ''')
        # Autonaprawa: Dodaj kolumnę, jeśli jej nie ma (dla istniejącej bazy)
        try:
            self.cursor.execute("ALTER TABLE historia_transakcji ADD COLUMN czas_wyjscia REAL")
        except: pass

        # 4. PAMIĘĆ MÓZGU
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS pamiec_mozgu (
                klucz_id TEXT PRIMARY KEY,
                symbol TEXT,
                typ_strategii TEXT,
                ostatni_wynik_proc REAL,
                liczba_wygranych INTEGER DEFAULT 0,
                liczba_przegranych INTEGER DEFAULT 0,
                status TEXT DEFAULT 'OCZEKUJE'
            )
        ''')

        # 5. HISTORIA ŚWIEC
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS historia_swiec (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT,
                interwal TEXT,
                timestamp INTEGER,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                rsi REAL DEFAULT 0
            )
        ''')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_swiece ON historia_swiec (symbol, interwal, timestamp)')
        self.conn.commit()

    # --- METODY PORTFELA ---
    def pobierz_saldo(self):
        self.cursor.execute('SELECT saldo_gotowka, zablokowany FROM portfel WHERE id=1')
        return self.cursor.fetchone()

    def aktualizuj_saldo(self, kwota_zmiany):
        self.cursor.execute('UPDATE portfel SET saldo_gotowka = saldo_gotowka + ? WHERE id=1', (kwota_zmiany,))
        self.conn.commit()

    # --- METODY POZYCJI ---
    def dodaj_pozycje(self, symbol, typ, cena, ilosc, zrodlo, powod):
        unikalne_id = f"{symbol}_{typ}"
        try:
            self.cursor.execute('''
                INSERT INTO aktywne_pozycje (unikalne_id, symbol, typ_strategii, cena_wejscia, ilosc, czas_wejscia, zrodlo, analiza_ai)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (unikalne_id, symbol, typ, cena, ilosc, time.time(), zrodlo, powod))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def usun_pozycje(self, symbol, typ_strategii):
        unikalne_id = f"{symbol}_{typ_strategii}"
        self.cursor.execute('SELECT * FROM aktywne_pozycje WHERE unikalne_id=?', (unikalne_id,))
        poz = self.cursor.fetchone()
        if poz:
            self.cursor.execute('DELETE FROM aktywne_pozycje WHERE unikalne_id=?', (unikalne_id,))
            self.conn.commit()
            return poz
        return None

    # 🔥 To jest funkcja, której brakowało w Twojej wersji, a jest konieczna dla Ewaluatora
    def aktualizuj_max_zysk(self, unikalne_id, nowy_max):
        self.cursor.execute('UPDATE aktywne_pozycje SET max_zysk = ? WHERE unikalne_id = ?', (nowy_max, unikalne_id))
        self.conn.commit()

    # --- METODY HISTORII I MÓZGU ---
    def zapisz_historie_transakcji(self, symbol, typ, zysk_usdt, zysk_proc, powod):
        # ZMIANA 3: Zapisujemy też czas_wyjscia (dla Skanera)
        teraz = time.time()
        self.cursor.execute('''
            INSERT INTO historia_transakcji (symbol, typ_strategii, zysk_usdt, zysk_proc, czas_zamkniecia, powod, czas_wyjscia)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (symbol, typ, zysk_usdt, zysk_proc, teraz, powod, teraz))
        self.conn.commit()

    def aktualizuj_strategie_mozgu(self, symbol, typ, wynik_proc, status="ZAKONCZONA"):
        klucz = f"{symbol}_{typ}"
        self.cursor.execute('SELECT liczba_wygranych, liczba_przegranych FROM pamiec_mozgu WHERE klucz_id=?', (klucz,))
        row = self.cursor.fetchone()
        
        if row:
            wyg = row[0] + (1 if wynik_proc > 0 else 0)
            przeg = row[1] + (1 if wynik_proc < 0 else 0)
            self.cursor.execute('''
                UPDATE pamiec_mozgu 
                SET ostatni_wynik_proc=?, liczba_wygranych=?, liczba_przegranych=?, status=?
                WHERE klucz_id=?
            ''', (wynik_proc, wyg, przeg, status, klucz))
        else:
            wyg = 1 if wynik_proc > 0 else 0
            przeg = 1 if wynik_proc < 0 else 0
            self.cursor.execute('''
                INSERT INTO pamiec_mozgu (klucz_id, symbol, typ_strategii, ostatni_wynik_proc, liczba_wygranych, liczba_przegranych, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (klucz, symbol, typ, wynik_proc, wyg, przeg, status))
        self.conn.commit()

    def zapisz_swiece(self, symbol, interwal, swiece_lista):
        for s in swiece_lista:
            self.cursor.execute('''
                INSERT OR IGNORE INTO historia_swiec (symbol, interwal, timestamp, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (symbol, interwal, s['time'], s['open'], s['high'], s['low'], s['close'], s['vol']))
        self.conn.commit()

    def znajdz_dno_historyczne(self, symbol, interwal, dni_wstecz=30):
        sekundy_wstecz = dni_wstecz * 24 * 3600
        cutoff = time.time() - sekundy_wstecz
        self.cursor.execute('SELECT MIN(low) FROM historia_swiec WHERE symbol=? AND interwal=? AND timestamp > ?', (symbol, interwal, cutoff))
        wynik = self.cursor.fetchone()
        return wynik[0] if wynik and wynik[0] else None

    def zamknij(self):
        self.conn.close()

