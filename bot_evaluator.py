import json
import time
import os
import sys
from datetime import datetime

# ============================================================
# 🛡️ BOT EVALUATOR V12.0 (SMART CLOSE + ADVANCED GHOSTS)
# ============================================================

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    import portfel_manager as pm
    from database_handler import DatabaseHandler
    # Wgrywamy całą Twoją skrzynkę z narzędziami!
    from utils_data import (calc_rsi, get_trend, analizuj_dynamike_swiecy, 
                            znajdz_wsparcia_i_opory, okresl_strukture_rynku, badaj_sile_wzgledem_btc)
except ImportError:
    print("   ⚠️ KRYTYCZNY BŁĄD: Brak modułów bazowych lub utils_data!")
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

def analizuj_rotacje_kapitalu(rynek_data, interwal="1h"):
    try:
        wzrosty = []
        spadki = []
        data_section = rynek_data.get("data", {})
        for sym, sym_data in data_section.items():
            swiece = sym_data.get(interwal, [])
            if len(swiece) >= 2:
                ost = swiece[-1]
                op = float(ost.get('open', ost.get('o', ost.get('c', 1))))
                cl = float(ost.get('close', ost.get('c', 1)))
                zmiana = ((cl - op) / op) * 100
                if zmiana > 0.5: wzrosty.append(sym)
                elif zmiana < -0.5: spadki.append(sym)
                
        if "BTC" in spadki and len(wzrosty) > len(spadki):
            return {"status": "ALT_POMPA", "opis": "BTC spada, alty rosną"}
        elif "BTC" in wzrosty and len(spadki) > len(wzrosty):
            return {"status": "BTC_DRENAZ", "opis": "BTC ssie kapitał, alty spadają"}
        elif len(wzrosty) > len(spadki):
            return {"status": "HOSSA", "opis": "Większość rynku rośnie"}
        elif len(spadki) > len(wzrosty):
            return {"status": "BESSA", "opis": "Większość rynku spada"}
        else:
            return {"status": "KONSOLIDACJA", "opis": "Rynek niezdecydowany"}
    except Exception:
        return {"status": "NIEZNANY", "opis": "Błąd analizy"}

def main():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🛡️ EVALUATOR V12.0: Weryfikacja (Ludzki Instynkt & Pro-Ghosts)...")
    
    rynek = wczytaj_json(PLIK_RYNKU)
    
    rotacja = analizuj_rotacje_kapitalu(rynek)
    status_rotacji = rotacja.get("status", "NIEZNANY")
    print(f"   🔄 ROTACJA KAPITAŁU: {rotacja.get('opis', 'Nieznana')}")

    try:
        sentyment_val = int(rynek.get("sentiment", {}).get("value", 50))
    except: sentyment_val = 50

    mnoznik_sl = 1.0
    mnoznik_trail = 1.0   
    tryb_opis = "NEUTRAL"

    if sentyment_val <= 25:
        tryb_opis = "EXTREME FEAR 💀"
        mnoznik_sl = 0.6
        mnoznik_trail = 0.5
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
    else:
        for pozycja in pozycje_sql:
            try:
                unikalne_id, symbol, typ_strat, cena_wej, ilosc, czas_wejscia, zrodlo, max_zysk = pozycja

                if zrodlo == "SKANER": continue

                cena_akt = pobierz_cene(rynek, symbol)
                if cena_akt == 0: continue

                wynik_proc = ((cena_akt - cena_wej) / cena_wej) * 100
                czas_trwania_min = (time.time() - czas_wejscia) / 60
                
                if wynik_proc > max_zysk:
                    max_zysk = wynik_proc
                    db.aktualizuj_max_zysk(unikalne_id, max_zysk)

                # ==========================================
                # 👁️ WZROK BOTA (PEŁNA ANALIZA PRICE ACTION)
                # ==========================================
                trend = "nieznany"
                rsi = 50.0
                vol_ratio = 1.0
                struktura = "Nieznana"
                korelacja = "BRAK"
                ksztalt = "Nieznany"
                dyst_wsp = 0.0
                dyst_opor = 0.0
                wsparcie = None
                opor = None

                try:
                    sym_short = symbol.replace("USDT", "")
                    swiece = rynek.get("data", {}).get(sym_short, {}).get("1h", [])
                    if not swiece: swiece = rynek.get("data", {}).get(symbol, {}).get("1h", [])

                    if swiece and len(swiece) >= 20:
                        ceny = [float(s.get('c', s.get('close', 0))) for s in swiece]
                        volumeny = [float(s.get('v', s.get('vol', 0))) for s in swiece]
                        
                        sma_20 = sum(ceny[-20:]) / 20
                        trend = "wzrost" if cena_akt > sma_20 else "spadek"
                        
                        avg_vol = sum(volumeny[-5:]) / 5 if sum(volumeny[-5:]) > 0 else 1
                        vol_ratio = volumeny[-1] / avg_vol if avg_vol > 0 else 0
                        rsi = calc_rsi(swiece)
                        
                        # Nowe funkcje "oczu"
                        struktura = okresl_strukture_rynku(swiece)
                        korelacja = badaj_sile_wzgledem_btc(rynek, swiece, "1h")
                        ksztalt = analizuj_dynamike_swiecy(swiece[-1])
                        wsparcie, opor = znajdz_wsparcia_i_opory(swiece, cena_akt)
                        
                        if wsparcie: dyst_wsp = ((cena_akt - wsparcie) / wsparcie) * 100
                        if opor: dyst_opor = ((opor - cena_akt) / cena_akt) * 100
                        
                except Exception as e: pass

                limit_display = LIMITS.get(typ_strat.split('_')[0], LIMITS["default"])
                kolor = '🟢' if wynik_proc > 0 else '🔴'
                
                # Bot głośno myśli na ekranie
                info_pa = f"Str: {struktura.split(' ')[0]}"
                if opor and wsparcie: info_pa += f" | Opor: +{dyst_opor:.1f}% | Wsp: -{dyst_wsp:.1f}%"
                
                print(f"   📊 {symbol:<6} [{typ_strat}] | {kolor} {wynik_proc:+.2f}% (Max:{max_zysk:.1f}%) | Czas: {format_czas(czas_trwania_min)}/{format_czas(limit_display)}")
                print(f"      👁️ {trend.upper()} | RSI: {rsi:.0f} | Vol: {vol_ratio:.1f}x | {info_pa}")

                decyzja_zamkniecia = False
                powod = ""

                # ==========================================
                # 🧠 INTELIGENTNE DECYZJE Z UŻYCIEM HIERARCHII
                # ==========================================
                
                trail_dist = 0.3 * mnoznik_trail
                if "4-godz" in typ_strat: trail_dist = 1.0 * mnoznik_trail
                elif "jednodniowa" in typ_strat: trail_dist = 2.0 * mnoznik_trail
                elif "tygodniowa" in typ_strat: trail_dist = 3.5 * mnoznik_trail

                # --- 1. Sztywne ramy (Ultimate Backup) ---
                if wynik_proc <= (-2.0 * mnoznik_sl) and "godz" in typ_strat: decyzja_zamkniecia = True; powod = f"Stop Loss (Krytyczny)"
                elif wynik_proc <= (-5.0 * mnoznik_sl): decyzja_zamkniecia = True; powod = f"Stop Loss (Krytyczny)"
                elif czas_trwania_min >= limit_display: decyzja_zamkniecia = True; powod = f"Koniec Czasu"
                
                # --- 2. LUDZKI INSTYNKT (Smart Close na podstawie Price Action) ---
                elif wynik_proc > 0.5:
                    
                    # Scenariusz A: Wyczerpanie (Wolumen zdycha, RSI opada, struktura się łamie)
                    if vol_ratio < 0.6 and rsi < 50 and "Niedźwiedzia" in struktura:
                        decyzja_zamkniecia = True
                        powod = "Smart Close (Wyczerpanie: rynek traci siłę, ucinam)"
                        
                    # Scenariusz B: Uderzenie w sufit (Realizacja zysków bez pazerności)
                    elif opor and dyst_opor < 0.5 and rsi > 65:
                        decyzja_zamkniecia = True
                        powod = f"Smart Take Profit (Uderzenie w opór {opor:.2f}, wycofuję się)"
                        
                    # Scenariusz C: Pęknięcie podłogi (Prawdziwy Trailing Stop)
                    elif wsparcie and cena_akt < wsparcie:
                        decyzja_zamkniecia = True
                        powod = f"Smart Trailing (Pęknięcie wsparcia {wsparcie:.2f})"
                        
                    # Klasyczny dynamiczny trailing (dla bezpieczeństwa, jeśli nie ma wsparcia)
                    elif max_zysk >= (trail_dist * 2) and wynik_proc < (max_zysk - trail_dist):
                        decyzja_zamkniecia = True
                        powod = f"Zabezpieczenie Zysku (Spadek z {max_zysk:.1f}%)"

                # ==========================================
                # 🛑 EGZEKUCJA I ZAPIS DUCHA (FORMALNY AUDYT)
                # ==========================================
                if decyzja_zamkniecia:
                    print("="*50)
                    print(f"   🔔 GŁÓWNY BOT: ZAMYKAM {symbol} [{typ_strat}]")
                    akcja_str = "KONIEC CZASU" if "Koniec" in powod or "Limit" in powod else powod
                    print(f"   📉 Akcja:        {akcja_str}")
                    print(f"   ⏱️ Czas trwania: {format_czas(czas_trwania_min)}")
                    print(f"   💵 Cena wejścia: {cena_wej:.4f}")
                    print(f"   💵 Cena wyjścia: {cena_akt:.4f}")
                    
                    zysk_usdt = pm.zwroc_srodki(symbol, cena_akt, zrodlo="MAIN_BOT", typ_strategii=typ_strat)
                    
                    try:
                        decyzja_short = "TP" if wynik_proc > 0 else "SL"
                        if "Koniec" in powod: decyzja_short = "TIME"
                        elif "Smart" in powod: decyzja_short = "SMART"
                        elif "Break" in powod or "Zabezpieczenie" in powod: decyzja_short = "BE"
                        
                        # 💾 Kompletny, ludzki odcisk palca
                        dane_wzorca = {
                            "trend": trend,
                            "rsi": rsi,
                            "vol_ratio": vol_ratio,
                            "sentyment": sentyment_val,
                            "korelacja_rynku": korelacja,
                            "stan_makro": status_rotacji,
                            "struktura": struktura,
                            "ksztalt_swiecy": ksztalt,
                            "dystans_wsparcie": dyst_wsp,
                            "dystans_opor": dyst_opor,
                            "wynik_proc": wynik_proc,
                            "decyzja": decyzja_short
                        }
                        
                        wzorzec_id = db.dodaj_wzorzec(symbol, typ_strat, dane_wzorca)
                        czas_pozostaly = limit_display - czas_trwania_min
                        
                        # 🔥 LOGIKA DUCHA (Odlicza resztę strategii) 🔥
                        if decyzja_short != "TIME" and czas_pozostaly > 5:
                            db.dodaj_ducha(wzorzec_id, symbol, typ_strat, cena_akt, czas_obserwacji_minut=czas_pozostaly)
                            print(f"   👻 [AUDYT WŁĄCZONY] Duch przypięty do wzorca (ID:{wzorzec_id}). Bada resztę strategii: {format_czas(czas_pozostaly)}.")
                        else:
                            roznica = max_zysk - wynik_proc
                            if roznica >= 2.0:
                                db.cursor.execute('UPDATE wzorce_rynkowe SET ocena_ducha = 0 WHERE id = ?', (wzorzec_id,))
                            else:
                                db.cursor.execute('UPDATE wzorce_rynkowe SET ocena_ducha = 1 WHERE id = ?', (wzorzec_id,))
                                
                    except Exception as e:
                        print(f"   ⚠️ Błąd SQL Wzorca/Ducha: {e}")
                    
                    db.aktualizuj_strategie_mozgu(symbol, typ_strat, wynik_proc, status="ZAKONCZONA")
                    print(f"   💾 [SQL] Zaktualizowano inteligencję dla {symbol} ({wynik_proc:.2f}%)")

                    print(f"   💰 WYNIK:        ⌛ {wynik_proc:+.2f}% (Max: {max_zysk:.2f}%)")
                    print(f"   📝 Powód:        {powod}")
                    print(f"   🏦 PORTFEL:      {'🟢' if zysk_usdt > 0 else '🔴'} {zysk_usdt:+.2f} USDT")
                    print("="*50)
                    print("                                                        💾 Baza zaktualizowana natychmiast.")
                    try: db.conn.commit()
                    except: pass

            except Exception as e:
                continue

    # ==========================================
    # 👻 GHOST TRACKER - AKTUALIZACJA I FORMALNE RAPORTY
    # ==========================================
    try:
        duchy = db.pobierz_aktywne_duchy()
        if duchy:
            print(f"\n   👻 [GHOST TRACKER] Obserwuję {len(duchy)} zamkniętych pozycji...")
            teraz = time.time()
            
            for d in duchy:
                duch_id, w_id, d_symbol, c_zamk, max_c, min_c = d
                akt_cena_ducha = pobierz_cene(rynek, d_symbol)
                if akt_cena_ducha > 0:
                    db.aktualizuj_ducha(duch_id, akt_cena_ducha)
                    
            db.cursor.execute('SELECT id, wzorzec_id, symbol, typ_strategii, cena_zamkniecia, max_cena_ghost, min_cena_ghost FROM ghost_trades WHERE zakonczony = 0 AND czas_obserwacji_do <= ?', (teraz,))
            zakonczone = db.cursor.fetchall()
            
            for zd in zakonczone:
                d_id, w_id, sym, typ, c_zamk, max_c, min_c = zd
                
                max_wzrost = ((max_c - c_zamk) / c_zamk) * 100
                max_spadek = ((min_c - c_zamk) / c_zamk) * 100
                
                ocena = 1 
                
                # Zmienność progu w zależności od długości strategii (Tygodniówka potrzebuje więcej luzu niż godzinówka)
                prog_bledu = 1.5 if "godzinowa" in typ else (3.0 if "4-godz" in typ else 5.0)
                
                if max_wzrost >= prog_bledu:
                    wniosek = f"BŁĄD ❌ (Ucięto za wcześnie. W pozostałym czasie rynek wybił o +{max_wzrost:.1f}%)"
                    ocena = 0 
                elif max_spadek <= -prog_bledu:
                    wniosek = f"SUKCES ✅ (Trafna diagnoza oporu. Uratowano kapitał przed zjazdem {max_spadek:.1f}%)"
                elif max_wzrost > abs(max_spadek):
                    wniosek = f"LEKKI BŁĄD ⚠️ (Odbiło na +{max_wzrost:.1f}%. Przedwczesna panika na wsparciu)"
                    ocena = 0
                else:
                    wniosek = f"DOBRA DECYZJA 🛡️ (Rynek wyczerpał siłę. Ominęliśmy zjazd {max_spadek:.1f}%)"
                    
                print(f"   📋 [RAPORT AUDYTU] {sym} [{typ}]: {wniosek}")
                db.zakoncz_ducha_i_ocen_wzorzec(d_id, w_id, ocena)
                
    except Exception as e:
        pass

if __name__ == "__main__":
    main()