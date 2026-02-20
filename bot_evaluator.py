import json
import time
import os
import sys
from datetime import datetime

# ============================================================
# 🛡️ BOT EVALUATOR V11.7 (FIX: DYNAMIC TRAILING & 6 SLOTS)
# ============================================================

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    import portfel_manager as pm
    from database_handler import DatabaseHandler
except ImportError:
    print("   ⚠️ KRYTYCZNY BŁĄD: Brak modułu portfel_manager lub database_handler!")
    sys.exit()

db = DatabaseHandler()
PLIK_RYNKU = "rynek.json"

LIMITS = {
    "godzinowa": 60,       # 1h
    "4-godzinna": 240,     # 4h
    "jednodniowa": 1500,   # 25h
    "tygodniowa": 10080,   # 7 dni
    "moonshot": 60,        # 1h
    "default": 120
}

def wczytaj_json(plik):
    if not os.path.exists(plik): return {}
    try:
        with open(plik, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def format_czas(minuty):
    if minuty < 60: return f"{int(minuty)}m"
    return f"{int(minuty//60)}h {int(minuty%60)}m"

def pobierz_cene(rynek, symbol):
    warianty = [symbol, symbol.replace("USDT", ""), symbol + "USDT"]
    if "prices" in rynek and isinstance(rynek["prices"], list):
        for p in rynek["prices"]:
            if p.get("symbol") in warianty: return float(p.get("current_price", 0))
    if "data" in rynek:
        for wariant in warianty:
            if wariant in rynek["data"]:
                val = rynek["data"][wariant]
                return float(val.get("lastPrice", 0)) if isinstance(val, dict) else float(val)
    return 0.0

def main():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🛡️ EVALUATOR V11.7: Weryfikacja (Dynamic Trailing)...")
    
    rynek = wczytaj_json(PLIK_RYNKU)
    
    try:
        sentyment_val = int(rynek.get("sentiment", {}).get("value", 50))
    except: sentyment_val = 50

    mnoznik_sl = 1.0
    mnoznik_trail = 1.0   
    tryb_opis = "NEUTRAL"

    # --- LOGIKA SENTYMENTU (ZACIŚNIĘCIE W STRACHU) ---
    if sentyment_val <= 25:
        tryb_opis = "EXTREME FEAR 💀"
        mnoznik_sl = 0.6
        mnoznik_trail = 0.5    # Trailing 2x ciaśniejszy!
    elif sentyment_val <= 40:
        tryb_opis = "FEAR 😨"
        mnoznik_sl = 0.8
        mnoznik_trail = 0.75
    elif sentyment_val >= 75:
        tryb_opis = "EXTREME GREED 🤑"
        mnoznik_sl = 1.0
        mnoznik_trail = 1.0
    else:
        tryb_opis = "NEUTRAL/GREED 🙂"

    if mnoznik_sl < 1.0:
        print(f"   ⚠️ RYNEK: {tryb_opis} (SL x{mnoznik_sl}, Trail x{mnoznik_trail}) - TRYB OCHRONNY")

    try:
        db.cursor.execute("SELECT unikalne_id, symbol, typ_strategii, cena_wejscia, ilosc, czas_wejscia, zrodlo, max_zysk FROM aktywne_pozycje")
        pozycje_sql = db.cursor.fetchall()
    except Exception as e:
        print(f"⚠️ Błąd pobierania pozycji z SQL: {e}")
        return

    if not pozycje_sql:
        print("   (Brak aktywnych pozycji)")
        return

    for pozycja in pozycje_sql:
        try:
            unikalne_id = pozycja[0]
            symbol = pozycja[1]
            typ_strat = pozycja[2]
            cena_wej = float(pozycja[3])
            ilosc = float(pozycja[4])
            czas_wejscia = float(pozycja[5])
            zrodlo = pozycja[6]
            max_zysk = float(pozycja[7]) if pozycja[7] is not None else 0.0

            if zrodlo == "SKANER": continue

            cena_akt = pobierz_cene(rynek, symbol)
            if cena_akt == 0: continue

            wynik_proc = ((cena_akt - cena_wej) / cena_wej) * 100
            czas_trwania_min = (time.time() - czas_wejscia) / 60
            
            if wynik_proc > max_zysk:
                max_zysk = wynik_proc
                db.aktualizuj_max_zysk(unikalne_id, max_zysk)

            limit_display = LIMITS["default"]
            if "jednodniowa" in typ_strat: limit_display = LIMITS["jednodniowa"]
            elif "tygodniowa" in typ_strat: limit_display = LIMITS["tygodniowa"]
            elif "4-godz" in typ_strat: limit_display = LIMITS["4-godzinna"]
            elif "godz" in typ_strat: limit_display = LIMITS["godzinowa"]
            elif "moonshot" in typ_strat: limit_display = LIMITS["moonshot"]

            kolor = '🟢' if wynik_proc > 0 else '🔴'
            print(f"   📊 {symbol:<6} [{typ_strat}] | {kolor} {wynik_proc:+.2f}% (Max:{max_zysk:.1f}%) | Czas: {format_czas(czas_trwania_min)}/{format_czas(limit_display)}")

            decyzja_zamkniecia = False
            powod = ""

            # --- LOGIKA DECYZYJNA (NAPRAWIONA) ---

            if "godzinowa" in typ_strat:
                trail_dist = 0.3 * mnoznik_trail
                if trail_dist < 0.15: trail_dist = 0.15

                if wynik_proc >= 1.5: decyzja_zamkniecia = True; powod = f"Take Profit (+{wynik_proc:.2f}%)"
                elif wynik_proc <= (-1.5 * mnoznik_sl): decyzja_zamkniecia = True; powod = f"Stop Loss (Limit {-1.5 * mnoznik_sl:.1f}%)"
                elif czas_trwania_min >= LIMITS["godzinowa"]: decyzja_zamkniecia = True; powod = f"Koniec Czasu (Limit 1h)"
                elif max_zysk >= (0.8 * mnoznik_trail) and wynik_proc <= 0.1: decyzja_zamkniecia = True; powod = "Break Even (Ochrona Kapitału)"

            elif "4-godz" in typ_strat:
                trail_dist = 1.0 * mnoznik_trail
                if max_zysk > 4.0: trail_dist = 0.5 * mnoznik_trail

                if wynik_proc >= 4.0: decyzja_zamkniecia = True; powod = f"Take Profit (+{wynik_proc:.2f}%)"
                elif wynik_proc <= (-3.0 * mnoznik_sl): decyzja_zamkniecia = True; powod = f"Stop Loss (Limit {-3.0 * mnoznik_sl:.1f}%)"
                
                # Dynamiczny Trailing
                elif max_zysk >= (1.5 * mnoznik_trail) and wynik_proc < (max_zysk - trail_dist): 
                    decyzja_zamkniecia = True; powod = f"Trailing Stop (Zjazd z {max_zysk:.1f}%)"
                
                elif max_zysk >= (1.5 * mnoznik_trail) and wynik_proc <= 0.2: decyzja_zamkniecia = True; powod = "Break Even (Ochrona Zysku)"
                elif czas_trwania_min >= LIMITS["4-godzinna"]: decyzja_zamkniecia = True; powod = f"Koniec Czasu (Limit 4h)"

            elif "jednodniowa" in typ_strat:
                trail_dist = 2.0 * mnoznik_trail
                
                if wynik_proc >= 8.0: decyzja_zamkniecia = True; powod = f"Take Profit (+{wynik_proc:.2f}%)"
                elif wynik_proc <= (-5.0 * mnoznik_sl): decyzja_zamkniecia = True; powod = f"Stop Loss (Limit {-5.0 * mnoznik_sl:.1f}%)"
                elif max_zysk >= (3.0 * mnoznik_trail) and wynik_proc < (max_zysk - trail_dist): 
                    decyzja_zamkniecia = True; powod = f"Trailing Stop (Daily)"
                elif czas_trwania_min >= LIMITS["jednodniowa"]: decyzja_zamkniecia = True; powod = f"Koniec Czasu (Limit 25h)"

            # --- TYGODNIOWA (FIX: DYNAMICZNY LUZ) ---
            elif "tygodniowa" in typ_strat:
                trail_dist = 3.5 * mnoznik_trail 
                if trail_dist < 1.0: trail_dist = 1.0

                if wynik_proc >= 20.0: decyzja_zamkniecia = True; powod = f"Take Profit (+{wynik_proc:.2f}%)"
                elif wynik_proc <= (-8.0 * mnoznik_sl): decyzja_zamkniecia = True; powod = f"Stop Loss (Limit {-8.0 * mnoznik_sl:.1f}%)"
                elif max_zysk >= 4.0 and wynik_proc <= 0.5: decyzja_zamkniecia = True; powod = "Break Even (Weekly)"
                
                # Używamy trail_dist zamiast sztywnej 4.0
                elif max_zysk >= (6.0 * mnoznik_trail) and wynik_proc < (max_zysk - trail_dist): 
                    decyzja_zamkniecia = True; powod = f"Trailing Stop (Zjazd z {max_zysk:.1f}%)"
                
                elif czas_trwania_min >= LIMITS["tygodniowa"]: decyzja_zamkniecia = True; powod = "Koniec Czasu (7 dni)"

            elif "moonshot" in typ_strat:
                trail_dist = 3.0 * mnoznik_trail 
                if max_zysk >= 10.0 and wynik_proc < (max_zysk - trail_dist): decyzja_zamkniecia = True; powod = "Trailing Moonshot"
                elif wynik_proc <= (-4.0 * mnoznik_sl): decyzja_zamkniecia = True; powod = "Stop Loss Moonshot"
                elif czas_trwania_min >= LIMITS["moonshot"]: decyzja_zamkniecia = True; powod = "Koniec Czasu Moonshot"
            
            else:
                if wynik_proc >= 2.5: decyzja_zamkniecia = True; powod = "TP Default"
                elif wynik_proc <= -2.0: decyzja_zamkniecia = True; powod = "SL Default"
                elif czas_trwania_min >= 120: decyzja_zamkniecia = True; powod = "Timeout Default"

            if decyzja_zamkniecia:
                print("="*50)
                print(f"   🔔 GŁÓWNY BOT: ZAMYKAM {symbol} [{typ_strat}]")
                akcja_str = "KONIEC CZASU" if "Koniec" in powod or "Limit" in powod else powod
                print(f"   📉 Akcja:        {akcja_str}")
                print(f"   ⏱️ Czas trwania: {format_czas(czas_trwania_min)}")
                print(f"   💵 Cena wejścia: {cena_wej:.4f}")
                print(f"   💵 Cena wyjścia: {cena_akt:.4f}")
                
                zysk_usdt = pm.zwroc_srodki(symbol, cena_akt, zrodlo="MAIN_BOT", typ_strategii=typ_strat)
                
                db.aktualizuj_strategie_mozgu(symbol, typ_strat, wynik_proc, status="ZAKONCZONA")
                print(f"   💾 [SQL] Zaktualizowano inteligencję dla {symbol} ({wynik_proc:.2f}%)")

                print(f"   💰 WYNIK:        ⌛ {wynik_proc:+.2f}% (Max: {max_zysk:.2f}%)")
                print(f"   📝 Powód:        {powod}")
                print(f"   🏦 PORTFEL:      {'🟢' if zysk_usdt > 0 else '🔴'} {zysk_usdt:+.2f} USDT")
                print("="*50)
                print("                                                                💾 Baza zaktualizowana natychmiast.")
                try: db.conn.commit()
                except: pass

        except Exception as e:
            continue

if __name__ == "__main__":
    main()