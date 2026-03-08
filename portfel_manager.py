import json
import os
import time
import sys
import math
import requests  # <-- Dodany moduł do Telegrama

# ============================================================
# 💰 PORTFEL MANAGER V11.1 (LIVE BINANCE + HYBRYDA + TELEGRAM)
# ============================================================

# ----------------- USTAWIENIA GIEŁDY -----------------
TRYB_REAL = False   # ⚠️ ZMIEŃ NA True, ABY HANDLOWAĆ PRAWDZIWYMI PIENIĘDZMI
API_KEY = 'TWÓJ_KLUCZ_BINANCE' # Pamiętaj żeby usunąć potem dając do repo
API_SECRET = 'TWÓJ_SECRET_BINANCE' # Pamiętaj żeby usunąć potem dając do repo
# -----------------------------------------------------

# ----------------- USTAWIENIA TELEGRAM -----------------
TELEGRAM_TOKEN = "TUTAJ_WKLEJ_TOKEN_OD_BOTFATHERA"
TELEGRAM_CHAT_ID = "TUTAJ_WKLEJ_SWOJ_CHAT_ID"

def wyslij_powiadomienie(wiadomosc):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or TELEGRAM_TOKEN == "TUTAJ_WKLEJ_TOKEN_OD_BOTFATHERA": return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": wiadomosc,
            "parse_mode": "HTML"
        }
        requests.post(url, data=payload, timeout=5)
    except Exception as e:
        print(f"⚠️ Błąd wysyłania na Telegram: {e}")
# -----------------------------------------------------

# Import biblioteki Binance (tylko jeśli zainstalowana)
try:
    from binance.client import Client
    from binance.enums import *
    from binance.exceptions import BinanceAPIException
    BINANCE_READY = True
except ImportError:
    BINANCE_READY = False
    print("⚠️ Błąd: Brak biblioteki python-binance. Uruchom: pip install python-binance")

# Inicjalizacja klienta Binance
if TRYB_REAL and BINANCE_READY:
    try:
        client = Client(API_KEY, API_SECRET)
        print("✅ [PORTFEL] Tryb REAL aktywny. Podłączono do Binance 🚀")
    except Exception as e:
        print(f"❌ [PORTFEL KRYTYCZNY] Błąd połączenia z Binance: {e}")
        TRYB_REAL = False
else:
    client = None
    print("🛡️ [PORTFEL] Tryb SYMULACJI (Paper Trading) - Prawdziwe zlecenia wyłączone.")


# Dodajemy ścieżkę do modułów
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Importujemy naszą nową bazę
try:
    from database_handler import DatabaseHandler
    db = DatabaseHandler() # Połączenie z bazą
    print("✅ Portfel połączony z bazą SQLite.")
except ImportError:
    print("❌ BŁĄD KRYTYCZNY: Brak pliku database_handler.py!")
    sys.exit()

# --- MIGRACJA STARYCH DANYCH ---
def migruj_z_jsona():
    plik_json = "portfel.json"
    if os.path.exists(plik_json):
        try:
            with open(plik_json, 'r') as f:
                dane = json.load(f)
                stare_saldo = float(dane.get("saldo_gotowka", 1000.0))
                
                # Sprawdzamy obecne saldo w bazie
                obecne_db = db.pobierz_saldo()[0]
                
                # Jeśli w bazie jest domyślne 1000, a w jsonie inne, to nadpisujemy
                if obecne_db == 1000.0 and stare_saldo != 1000.0:
                    roznica = stare_saldo - 1000.0
                    db.aktualizuj_saldo(roznica)
                    print(f"🔄 Zmigrowano saldo z JSON do SQL: {stare_saldo} USDT")
        except: pass

migruj_z_jsona()
# -------------------------------------------

PLIK_RYNKU = "rynek.json"
if not os.path.exists(PLIK_RYNKU) and os.path.exists(os.path.join("..", PLIK_RYNKU)):
    PLIK_RYNKU = os.path.join("..", PLIK_RYNKU)

def pobierz_cene_aktualna(symbol):
    if not os.path.exists(PLIK_RYNKU): return 0.0
    try:
        with open(PLIK_RYNKU, 'r', encoding='utf-8') as f:
            rynek = json.load(f)
            
        if "prices" in rynek and isinstance(rynek["prices"], list):
            for p in rynek["prices"]:
                if p.get("symbol") == symbol: return float(p.get("price", 0))
        
        if "data" in rynek:
            symbol_short = symbol.replace("USDT", "")
            if symbol in rynek["data"]:
                val = rynek["data"][symbol]
                return float(val.get("lastPrice", 0)) if isinstance(val, dict) else float(val)
            if symbol_short in rynek["data"]:
                val = rynek["data"][symbol_short]
                return float(val.get("lastPrice", 0)) if isinstance(val, dict) else float(val)
    except: pass
    return 0.0

def oblicz_wartosc_total():
    # 1. Gotówka z bazy
    try:
        saldo_gotowka = db.pobierz_saldo()[0]
    except: return 0.0
    
    # 2. Wartość pozycji z bazy
    wartosc_pozycji = 0.0
    
    try:
        db.cursor.execute("SELECT symbol, ilosc FROM aktywne_pozycje")
        pozycje = db.cursor.fetchall()
        
        for sym, ilosc in pozycje:
            cena_akt = pobierz_cene_aktualna(sym)
            if cena_akt == 0:
                db.cursor.execute("SELECT cena_wejscia FROM aktywne_pozycje WHERE symbol=?", (sym,))
                res = db.cursor.fetchone()
                if res: cena_akt = res[0]
            
            wartosc_pozycji += (ilosc * cena_akt)
            
    except Exception as e:
        print(f"⚠️ Błąd obliczania total: {e}")

    return saldo_gotowka + wartosc_pozycji

def wczytaj_portfel():
    try:
        saldo = db.pobierz_saldo()[0]
        db.cursor.execute("SELECT symbol, ilosc, cena_wejscia, zrodlo, typ_strategii, czas_wejscia, unikalne_id FROM aktywne_pozycje")
        rows = db.cursor.fetchall()
        pozycje_dict = {}
        
        for r in rows:
            sym = r[0]
            pozycje_dict[sym] = {
                "symbol": sym, 
                "ilosc": r[1], 
                "cena_wejscia": r[2], 
                "zrodlo": r[3], 
                "typ_strategii": r[4], 
                "czas_zakupu": r[5],
                "max_zysk": 0.0 
            }
        return {"saldo_gotowka": saldo, "saldo_usdt": saldo, "pozycje": pozycje_dict}
    except:
        return {"saldo_gotowka": 0, "pozycje": {}}

def zapisz_portfel(dane):
    pass 

def bezpieczne_zaokraglenie(ilosc):
    """Zabezpieczenie przed błędem LOT_SIZE na Binance (odcinanie końcówek)"""
    if ilosc >= 1000: return math.floor(ilosc)
    elif ilosc >= 10: return math.floor(ilosc * 10) / 10.0
    else: return math.floor(ilosc * 10000) / 10000.0


# =========================================================
# 🔥 GŁÓWNA FUNKCJA ZAKUPOWA (HYBRYDOWY SKANER + TELEGRAM)
# =========================================================
def pobierz_srodki(symbol, cena_akt, procent_kapitalu=0.10, zrodlo="SKANER", typ_strategii="STANDARD"):
    # 1. Sprawdzenie salda w SQL
    try:
        saldo = db.pobierz_saldo()[0]
    except: return False, 0, 0
    
    # Limit slotów dla Skanera
    if zrodlo == "SKANER":
        try:
            db.cursor.execute("SELECT count(*) FROM aktywne_pozycje WHERE zrodlo='SKANER'")
            aktywne_cnt = db.cursor.fetchone()[0]
            if aktywne_cnt >= 10: return False, 0, 0
        except: pass
        
        # 🟢 HYBRYDOWA STAWKA DLA SKANERA
        kalkulacja_procentowa = saldo * 0.07
        if kalkulacja_procentowa > 70.0:
            kwota = 70.0  # Limit górny (zabezpiecza przed poślizgiem)
        else:
            kwota = kalkulacja_procentowa # Skaluje się w dół (ratuje przy małym saldzie)
            
    elif zrodlo == "MAIN_BOT" or zrodlo == "GŁÓWNY_BOT":
        # Limit slotów dla Mózgu
        try:
            db.cursor.execute("SELECT count(*) FROM aktywne_pozycje WHERE zrodlo='MAIN_BOT' OR zrodlo='GŁÓWNY_BOT'")
            main_cnt = db.cursor.fetchone()[0]
            if main_cnt >= 6: return False, 0, 0
        except: pass

        total = oblicz_wartosc_total()
        kwota = total * 0.05 # Mózg gra procentem, bo ma dużą płynność na głównych monetach
    else:
        total = oblicz_wartosc_total()
        kwota = total * procent_kapitalu 

    if kwota > saldo: kwota = saldo
    if kwota < 5: return False, 0, 0 # Minimum 5$ dla bezpieczeństwa Binance

    ilosc_kupiona = kwota / cena_akt

    # -----------------------------------------
    # 🔴 EGZEKUCJA NA PRAWDZIWEJ GIEŁDZIE 🔴
    # -----------------------------------------
    if TRYB_REAL and client:
        try:
            order = client.create_order(
                symbol=symbol,
                side=SIDE_BUY,
                type=ORDER_TYPE_MARKET,
                quoteOrderQty=kwota
            )
            real_qty = float(order['executedQty'])
            real_cost = float(order['cummulativeQuoteQty'])
            cena_akt = real_cost / real_qty if real_qty > 0 else cena_akt
            ilosc_kupiona = real_qty
            kwota = real_cost
            print(f"   💸 [BINANCE LIVE] KUPIONO {symbol} za {kwota:.2f} USDT!")
        except BinanceAPIException as e:
            print(f"   ❌ [BINANCE BŁĄD KUPNA] {symbol}: {e.message}")
            return False, 0, 0
        except Exception as e:
            print(f"   ❌ [SYSTEM BŁĄD] {e}")
            return False, 0, 0
    
    # 2. Transakcja w SQL
    try:
        finalny_typ = "skalp" if zrodlo == "SKANER" else typ_strategii
        db.aktualizuj_saldo(-kwota)
        sukces = db.dodaj_pozycje(symbol, finalny_typ, cena_akt, ilosc_kupiona, zrodlo, "Kupno")
        
        if sukces:
            # 🔥 POWIADOMIENIE TELEGRAM
            msg = f"🛒 <b>NOWA POZYCJA ({zrodlo})</b>\nSymbol: #{symbol}\nCena: {cena_akt:.5f} USDT\nStawka: {kwota:.2f} USDT"
            wyslij_powiadomienie(msg)
            
            return True, ilosc_kupiona, kwota
        else:
            db.aktualizuj_saldo(kwota)
            return False, 0, 0
            
    except Exception as e:
        print(f"⚠️ Błąd SQL przy zakupie: {e}")
        return False, 0, 0

# =========================================================
# 🔥 FUNKCJA SPRZEDAŻY (INTEGRACJA LIVE + TELEGRAM)
# =========================================================
def zwroc_srodki(symbol, cena_wyjscia, zrodlo=None, typ_strategii=None):
    try:
        db.cursor.execute("SELECT * FROM aktywne_pozycje WHERE symbol=?", (symbol,))
        rows = db.cursor.fetchall()
        if not rows: return 0.0
        
        # --- LOGIKA WYBORU POZYCJI (SNAJPER) ---
        poz = None
        if typ_strategii:
            for r in rows:
                if r[2] == typ_strategii: 
                    poz = r
                    break
        
        if not poz and zrodlo:
            for r in rows:
                if zrodlo == "SKANER" and r[6] == "SKANER": poz = r; break
                if zrodlo != "SKANER" and r[6] != "SKANER": poz = r; break
        
        if not poz: poz = rows[0] 
        
        unikalne_id = poz[0]
        typ_strat_db = poz[2]
        cena_wej = poz[3]
        ilosc_db = poz[4]
        
        wartosc_wyjscia = ilosc_db * cena_wyjscia
        wartosc_wejscia = ilosc_db * cena_wej
        zysk_netto = wartosc_wyjscia - wartosc_wejscia
        
        # -----------------------------------------
        # 🔴 EGZEKUCJA NA PRAWDZIWEJ GIEŁDZIE 🔴
        # -----------------------------------------
        if TRYB_REAL and client:
            try:
                asset = symbol.replace('USDT', '')
                balance = client.get_asset_balance(asset=asset)
                dostepne_srodki = float(balance['free'])
                
                if dostepne_srodki > 0:
                    ilosc_do_sprzedazy = bezpieczne_zaokraglenie(min(ilosc_db, dostepne_srodki))
                    if ilosc_do_sprzedazy > 0:
                        order = client.create_order(
                            symbol=symbol,
                            side=SIDE_SELL,
                            type=ORDER_TYPE_MARKET,
                            quantity=ilosc_do_sprzedazy
                        )
                        przychod_usdt = float(order['cummulativeQuoteQty'])
                        real_qty = float(order['executedQty'])
                        cena_wyjscia = przychod_usdt / real_qty if real_qty > 0 else cena_wyjscia
                        wartosc_wyjscia = przychod_usdt
                        zysk_netto = wartosc_wyjscia - wartosc_wejscia
                        print(f"   💰 [BINANCE LIVE] SPRZEDANO {symbol}. Przychód: {przychod_usdt:.2f} USDT!")
                else:
                    print(f"   ⚠️ [BINANCE BŁĄD] Brak {asset} na koncie do sprzedaży! Używam symulacji awaryjnie.")
            except BinanceAPIException as e:
                print(f"   ❌ [BINANCE BŁĄD SPRZEDAŻY] {symbol}: {e.message}")
            except Exception as e:
                print(f"   ❌ [SYSTEM BŁĄD] {e}")

        zysk_proc = ((cena_wyjscia - cena_wej) / cena_wej) * 100
        
        # --- TRANSAKCJA SQL ---
        db.cursor.execute("DELETE FROM aktywne_pozycje WHERE unikalne_id=?", (unikalne_id,))
        db.aktualizuj_saldo(wartosc_wyjscia)
        db.zapisz_historie_transakcji(symbol, typ_strat_db, zysk_netto, zysk_proc, "Sprzedaż")
        
        if zrodlo != "SKANER":
            db.aktualizuj_strategie_mozgu(symbol, typ_strat_db, zysk_proc, "ZAKONCZONA")
            print(f"   💾 [SQL] Zaktualizowano inteligencję dla {symbol} ({zysk_proc:.2f}%)")

        db.conn.commit()
        
        # 🔥 POWIADOMIENIE TELEGRAM
        kolko = "🟢" if zysk_netto > 0 else "🔴"
        status = "ZYSK" if zysk_netto > 0 else "STRATA / CIĘCIE"
        msg = f"{kolko} <b>{status}</b>\nSymbol: #{symbol}\nWynik: {zysk_proc:+.2f}%\nZysk/Strata: {zysk_netto:+.2f} USDT"
        wyslij_powiadomienie(msg)

        return zysk_netto

    except Exception as e:
        print(f"⚠️ Błąd SQL przy sprzedaży: {e}")
        return 0.0