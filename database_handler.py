import os
import time

import psycopg2
import psycopg2.extras

PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = os.environ.get("PG_PORT", "5432")
PG_USER = os.environ.get("PG_USER", "postgres")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "postgres")
PG_DATABASE = os.environ.get("PG_DATABASE", "bot_db")
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
)


class SQLCursor:
    def __init__(self, raw_cursor):
        self._cursor = raw_cursor

    def _translate_query(self, query):
        if not isinstance(query, str):
            return query
        return query.replace("?", "%s")

    def execute(self, query, params=None):
        return self._cursor.execute(self._translate_query(query), params)

    def executemany(self, query, param_list):
        return self._cursor.executemany(self._translate_query(query), param_list)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class DatabaseHandler:
    def __init__(self, dsn=None):
        """Łączy się z PostgreSQL i tworzy tabele, jeśli nie istnieją."""
        self.dsn = dsn or DATABASE_URL
        self.conn = psycopg2.connect(self.dsn)
        self.conn.autocommit = False
        self.cursor = SQLCursor(self.conn.cursor())
        self._inicjalizuj_tabele()

    def close(self):
        try:
            self.cursor._cursor.close()
        except Exception:
            pass
        try:
            self.conn.close()
        except Exception:
            pass

    def _inicjalizuj_tabele(self):
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS portfel (
                id SERIAL PRIMARY KEY,
                saldo_gotowka REAL DEFAULT 1000.0,
                zablokowany BOOLEAN DEFAULT FALSE
            )
        ''')
        self.cursor.execute('SELECT count(*) FROM portfel WHERE id=1')
        if self.cursor.fetchone()[0] == 0:
            self.cursor.execute('INSERT INTO portfel (id, saldo_gotowka) VALUES (1, 1000.0)')

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
                max_zysk REAL DEFAULT 0.0
            )
        ''')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS historia_transakcji (
                id SERIAL PRIMARY KEY,
                symbol TEXT,
                typ_strategii TEXT,
                zysk_usdt REAL,
                zysk_proc REAL,
                czas_zamkniecia REAL,
                powod TEXT,
                czas_wyjscia REAL
            )
        ''')

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

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS historia_swiec (
                id SERIAL PRIMARY KEY,
                symbol TEXT,
                interwal TEXT,
                timestamp DOUBLE PRECISION,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume REAL,
                rsi REAL DEFAULT 0,
                UNIQUE(symbol, interwal, timestamp)
            )
        ''')
        self.cursor.execute('CREATE INDEX IF NOT EXISTS idx_swiece ON historia_swiec (symbol, interwal, timestamp)')

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS wzorce_rynkowe (
                id SERIAL PRIMARY KEY,
                symbol TEXT,
                typ_strategii TEXT,
                trend TEXT,
                rsi REAL,
                vol_ratio REAL,
                sentyment INTEGER,
                korelacja_rynku TEXT DEFAULT 'BRAK',
                stan_makro TEXT DEFAULT 'NIEZNANY',
                struktura_wykresu TEXT DEFAULT 'NIEZNANA',
                ksztalt_swiecy TEXT DEFAULT 'NIEZNANY',
                dystans_wsparcie REAL DEFAULT 0.0,
                dystans_opor REAL DEFAULT 0.0,
                wynik_proc REAL,
                decyzja TEXT,
                ocena_ducha INTEGER DEFAULT -1,
                czas_zapisu REAL
            )
        ''')

        for kol, typ in [
            ("korelacja_rynku", "TEXT DEFAULT 'BRAK'"),
            ("stan_makro", "TEXT DEFAULT 'NIEZNANY'"),
            ("struktura_wykresu", "TEXT DEFAULT 'NIEZNANA'"),
            ("ksztalt_swiecy", "TEXT DEFAULT 'NIEZNANY'"),
            ("dystans_wsparcie", "REAL DEFAULT 0.0"),
            ("dystans_opor", "REAL DEFAULT 0.0"),
            ("ocena_ducha", "INTEGER DEFAULT -1")
        ]:
            try:
                self.cursor.execute(f"ALTER TABLE wzorce_rynkowe ADD COLUMN {kol} {typ}")
            except Exception:
                pass

        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS ghost_trades (
                id SERIAL PRIMARY KEY,
                wzorzec_id INTEGER,
                symbol TEXT,
                typ_strategii TEXT,
                cena_zamkniecia REAL,
                czas_zamkniecia REAL,
                czas_obserwacji_do REAL,
                max_cena_ghost REAL,
                min_cena_ghost REAL,
                zakonczony BOOLEAN DEFAULT FALSE,
                cena_wejscia REAL DEFAULT 0.0,
                max_zysk_bota REAL DEFAULT 0.0
            )
        ''')
        for kol, typ in [
            ("wzorzec_id", "INTEGER"),
            ("cena_wejscia", "REAL DEFAULT 0.0"),
            ("max_zysk_bota", "REAL DEFAULT 0.0")
        ]:
            try:
                self.cursor.execute(f"ALTER TABLE ghost_trades ADD COLUMN {kol} {typ}")
            except Exception:
                pass

        self.conn.commit()

    def pobierz_saldo(self):
        self.cursor.execute('SELECT saldo_gotowka, zablokowany FROM portfel WHERE id=1')
        return self.cursor.fetchone()

    def aktualizuj_saldo(self, kwota_zmiany):
        self.cursor.execute('UPDATE portfel SET saldo_gotowka = saldo_gotowka + %s WHERE id=1', (kwota_zmiany,))
        self.conn.commit()

    def dodaj_pozycje(self, symbol, typ, cena, ilosc, zrodlo, powod):
        unikalne_id = f"{symbol}_{typ}"
        try:
            self.cursor.execute('''
                INSERT INTO aktywne_pozycje (unikalne_id, symbol, typ_strategii, cena_wejscia, ilosc, czas_wejscia, zrodlo, analiza_ai)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (unikalne_id, symbol, typ, cena, ilosc, time.time(), zrodlo, powod))
            self.conn.commit()
            return True
        except psycopg2.IntegrityError:
            self.conn.rollback()
            return False

    def usun_pozycje(self, symbol, typ_strategii):
        unikalne_id = f"{symbol}_{typ_strategii}"
        self.cursor.execute('SELECT * FROM aktywne_pozycje WHERE unikalne_id=%s', (unikalne_id,))
        poz = self.cursor.fetchone()
        if poz:
            self.cursor.execute('DELETE FROM aktywne_pozycje WHERE unikalne_id=%s', (unikalne_id,))
            self.conn.commit()
            return poz
        return None

    def aktualizuj_max_zysk(self, unikalne_id, nowy_max):
        self.cursor.execute('UPDATE aktywne_pozycje SET max_zysk = %s WHERE unikalne_id = %s', (nowy_max, unikalne_id))
        self.conn.commit()

    def zapisz_historie_transakcji(self, symbol, typ, zysk_usdt, zysk_proc, powod):
        teraz = time.time()
        self.cursor.execute('''
            INSERT INTO historia_transakcji (symbol, typ_strategii, zysk_usdt, zysk_proc, czas_zamkniecia, powod, czas_wyjscia)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (symbol, typ, zysk_usdt, zysk_proc, teraz, powod, teraz))
        self.conn.commit()

    def aktualizuj_strategie_mozgu(self, symbol, typ, wynik_proc, status="ZAKONCZONA"):
        klucz = f"{symbol}_{typ}"
        self.cursor.execute('SELECT liczba_wygranych, liczba_przegranych FROM pamiec_mozgu WHERE klucz_id=%s', (klucz,))
        row = self.cursor.fetchone()
        if row:
            wyg = row[0] + (1 if wynik_proc > 0 else 0)
            przeg = row[1] + (1 if wynik_proc < 0 else 0)
            self.cursor.execute('''
                UPDATE pamiec_mozgu 
                SET ostatni_wynik_proc=%s, liczba_wygranych=%s, liczba_przegranych=%s, status=%s
                WHERE klucz_id=%s
            ''', (wynik_proc, wyg, przeg, status, klucz))
        else:
            wyg = 1 if wynik_proc > 0 else 0
            przeg = 1 if wynik_proc < 0 else 0
            self.cursor.execute('''
                INSERT INTO pamiec_mozgu (klucz_id, symbol, typ_strategii, ostatni_wynik_proc, liczba_wygranych, liczba_przegranych, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (klucz, symbol, typ, wynik_proc, wyg, przeg, status))
        self.conn.commit()

    def zapisz_swiece(self, symbol, interwal, swiece_lista):
        for s in swiece_lista:
            self.cursor.execute('''
                INSERT INTO historia_swiec (symbol, interwal, timestamp, open, high, low, close, volume)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol, interwal, timestamp) DO NOTHING
            ''', (symbol, interwal, s['time'], s['open'], s['high'], s['low'], s['close'], s['vol']))
        self.conn.commit()

    def znajdz_dno_historyczne(self, symbol, interwal, dni_wstecz=30):
        sekundy_wstecz = dni_wstecz * 24 * 3600
        cutoff = time.time() - sekundy_wstecz
        self.cursor.execute('SELECT MIN(low) FROM historia_swiec WHERE symbol=%s AND interwal=%s AND timestamp > %s', (symbol, interwal, cutoff))
        wynik = self.cursor.fetchone()
        return wynik[0] if wynik and wynik[0] else None

    def dodaj_wzorzec(self, symbol, typ_strategii, trend, rsi, vol_ratio, sentyment, korelacja_rynku, stan_makro, struktura_wykresu, ksztalt_swiecy, dystans_wsparcie, dystans_opor, wynik_proc, decyzja):
        self.cursor.execute('''
            INSERT INTO wzorce_rynkowe (
                symbol, typ_strategii, trend, rsi, vol_ratio, sentyment, 
                korelacja_rynku, stan_makro, struktura_wykresu, ksztalt_swiecy, 
                dystans_wsparcie, dystans_opor, wynik_proc, decyzja, czas_zapisu
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        ''', (symbol, typ_strategii, trend, rsi, vol_ratio, sentyment, korelacja_rynku, stan_makro, struktura_wykresu, ksztalt_swiecy, dystans_wsparcie, dystans_opor, wynik_proc, decyzja, time.time()))
        wzorzec_id = self.cursor.fetchone()[0]
        self.conn.commit()
        return wzorzec_id

    def dodaj_ducha(self, wzorzec_id, symbol, typ_strategii, cena_zamkniecia, czas_obserwacji_minut, cena_wejscia=0.0, max_zysk_bota=0.0):
        """Wypuszcza Ducha przypiętego do konkretnego wzorca."""
        teraz = time.time()
        czas_do = teraz + (czas_obserwacji_minut * 60)
        self.cursor.execute('''
            INSERT INTO ghost_trades (
                wzorzec_id, symbol, typ_strategii, cena_zamkniecia, czas_zamkniecia, czas_obserwacji_do, 
                max_cena_ghost, min_cena_ghost, cena_wejscia, max_zysk_bota
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (wzorzec_id, symbol, typ_strategii, cena_zamkniecia, teraz, czas_do, cena_zamkniecia, cena_zamkniecia, cena_wejscia, max_zysk_bota))
        self.conn.commit()

    def pobierz_aktywne_duchy(self):
        teraz = time.time()
        self.cursor.execute('SELECT id, wzorzec_id, symbol, cena_zamkniecia, max_cena_ghost, min_cena_ghost FROM ghost_trades WHERE zakonczony = 0 AND czas_obserwacji_do > ?', (teraz,))
        return self.cursor.fetchall()

    def aktualizuj_ducha(self, duch_id, aktualna_cena):
        self.cursor.execute('SELECT max_cena_ghost, min_cena_ghost FROM ghost_trades WHERE id=?', (duch_id,))
        row = self.cursor.fetchone()
        if row:
            max_c = max(row[0], aktualna_cena)
            min_c = min(row[1], aktualna_cena)
            self.cursor.execute('UPDATE ghost_trades SET max_cena_ghost=?, min_cena_ghost=? WHERE id=?', (max_c, min_c, duch_id))
            self.conn.commit()

    def zakoncz_ducha_i_ocen_wzorzec(self, duch_id, wzorzec_id, ocena):
        """Formalny raport Ducha, który wbija twardą jedynkę (sukces) lub zero (błąd) do Pamięci Bota."""
        self.cursor.execute('UPDATE ghost_trades SET zakonczony = 1 WHERE id = ?', (duch_id,))
        if wzorzec_id:
            self.cursor.execute('UPDATE wzorce_rynkowe SET ocena_ducha = ? WHERE id = ?', (ocena, wzorzec_id))
        self.conn.commit()

    def oblicz_szanse_sukcesu(self, obecne_dane, decyzja_szukana="SMART"):
        """
        🔥 LUDZKA SKALA PODOBIEŃSTWA 🔥
        Zamiast odrzucać twardo rekordy, punktuje je na podstawie najważniejszych czynników (Wykres > RSI).
        """
        sentyment = obecne_dane.get('sentyment', 50)
        
        # Szufladka: Patrzymy tylko na historię z tym samym ogólnym nastrojem rynkowym
        self.cursor.execute('''
            SELECT struktura_wykresu, dystans_wsparcie, korelacja_rynku, trend, rsi, vol_ratio, ocena_ducha 
            FROM wzorce_rynkowe 
            WHERE decyzja = ? AND sentyment = ? AND ocena_ducha != -1
            ORDER BY id DESC LIMIT 200
        ''', (decyzja_szukana, sentyment))
        
        historia = self.cursor.fetchall()
        if not historia: return None
        
        przypadki_znajome = []
        
        for w in historia:
            w_struktura, w_wsp, w_korel, w_trend, w_rsi, w_vol, w_ocena = w
            punkty = 0
            
            # WAGA 1: Wykres i Struktura (35 pkt)
            if obecne_dane.get('struktura', '') == w_struktura: punkty += 35
            
            # WAGA 2: Położenie na wykresie - wsparcia (25 pkt)
            dystans = obecne_dane.get('dystans_wsparcie', 0)
            if abs(dystans - w_wsp) <= 1.0: punkty += 25
            
            # WAGA 3: Korelacja (Czarna Owca vs Reszta) (20 pkt)
            if obecne_dane.get('korelacja_rynku', '') == w_korel: punkty += 20
            
            # WAGA 4: Wskaźniki (10 pkt trend, 10 pkt RSI)
            if obecne_dane.get('trend', '') == w_trend: punkty += 10
            if abs(obecne_dane.get('rsi', 50) - w_rsi) <= 10: punkty += 10
            
            # Zaliczone tylko, jeśli bot czuje, że to ta sama sytuacja (min. 70/100 pkt)
            if punkty >= 70:
                przypadki_znajome.append(w_ocena)
                
        if len(przypadki_znajome) < 3: 
            return None # Za mało znajomych sytuacji, bot działa wg sztywnych zasad zapasowych
        
        sukcesy = sum(1 for p in przypadki_znajome if p == 1)
        szansa = (sukcesy / len(przypadki_znajome)) * 100
        return szansa

    def zamknij(self):
        self.conn.close()