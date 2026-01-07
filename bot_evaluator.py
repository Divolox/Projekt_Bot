import json
import time
import os
import sys
from datetime import datetime

# ============================================================
# 🛡️ BOT EVALUATOR (WERSJA OSTATECZNA - FIX CENY)
# ============================================================
# - ZACHOWANA LOGIKA "3 ŚWIATÓW" (OSOBNE BLOKI KODU)
# - NAPRAWIONE POBIERANIE CENY (Obsługa BTC i BTCUSDT)
# - SZTYWNE CZASY (60 min, 240 min, 1500 min)
# ============================================================

PLIK_PORTFELA = "portfel.json"
PLIK_RYNKU = "rynek.json"

# Sztywne limity czasowe (zgodnie z życzeniem)
LIMITS = {
    "godzinowa": 60,       # 1h
    "4-godzinna": 240,     # 4h
    "jednodniowa": 1500,   # 25h (24h + 1h zapasu na zamknięcie świecy)
    "tygodniowa": 10080,   # 7 dni
    "moonshot": 60,        # 1h (krótka pompa)
    "default": 120
}

def wczytaj_json(plik):
    """Bezpieczny odczyt"""
    if not os.path.exists(plik): return {}
    try:
        with open(plik, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        return {}

def zapisz_json(plik, dane):
    """Bezpieczny zapis"""
    try:
        with open(plik, 'w', encoding='utf-8') as f:
            json.dump(dane, f, indent=4)
    except Exception as e:
        pass

def format_czas(minuty):
    """Formatowanie czasu dla logów"""
    if minuty < 60: return f"{int(minuty)}m"
    return f"{int(minuty//60)}h {int(minuty%60)}m"

def pobierz_cene(rynek, symbol):
    """
    FIX: Funkcja pobierająca cenę, która sprawdza warianty z USDT i bez.
    Rozwiązuje problem 'Brak ceny dla BTC' gdy w rynku jest 'BTCUSDT'.
    """
    # Lista wariantów do sprawdzenia
    warianty = [symbol, symbol.replace("USDT", ""), symbol + "USDT"]
    
    # 1. Sprawdź format z BotObserwatora (lista 'prices')
    if "prices" in rynek and isinstance(rynek["prices"], list):
        for p in rynek["prices"]:
            # Sprawdzamy czy symbol z rynku pasuje do któregokolwiek wariantu
            if p.get("symbol") in warianty:
                return float(p.get("current_price", 0))

    # 2. Sprawdź format standardowy (słownik 'data')
    if "data" in rynek:
        for wariant in warianty:
            if wariant in rynek["data"]:
                val = rynek["data"][wariant]
                return float(val.get("lastPrice", 0)) if isinstance(val, dict) else float(val)
            
    return 0.0

def main():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🛡️ EVALUATOR: Weryfikacja (Smart Price Match)...")
    
    portfel = wczytaj_json(PLIK_PORTFELA)
    rynek = wczytaj_json(PLIK_RYNKU)
    
    if "pozycje" not in portfel or not portfel["pozycje"]:
        print("   (Brak aktywnych pozycji)")
        return

    try:
        import portfel_manager as pm
    except ImportError:
        print("   ⚠️ KRYTYCZNY BŁĄD: Brak modułu portfel_manager!")
        return

    # Iteracja po kopi słownika
    lista_pozycji = list(portfel["pozycje"].items())

    for symbol, poz in lista_pozycji:
        try:
            # 1. POMIJANIE SKANERA (On ma własną logikę w skaner_momentum.py)
            if poz.get("zrodlo") == "SKANER":
                continue

            typ_strat = poz.get("typ_strategii", "nieznany")
            
            # 2. POBIERANIE CENY (Z UŻYCIEM NOWEGO FIXA)
            cena_akt = pobierz_cene(rynek, symbol)
            
            if cena_akt == 0:
                print(f"   ⚠️ Brak ceny dla {symbol} (Sprawdź rynek.json)")
                continue

            # 3. OBLICZENIA WYNIKÓW
            cena_wej = float(poz["cena_wejscia"])
            # Fix dla ilości (obsługa starego i nowego klucza)
            ilosc = float(poz.get("ilosc", 0))
            if ilosc == 0: ilosc = float(poz.get("ilosc_coinow", 0))

            wynik_proc = ((cena_akt - cena_wej) / cena_wej) * 100
            
            czas_wejscia = poz.get("czas_zakupu", time.time())
            czas_trwania_min = (time.time() - czas_wejscia) / 60
            
            # Aktualizacja Max Zysku (dla Trailing Stopa)
            max_zysk = poz.get("max_zysk", 0.0)
            if wynik_proc > max_zysk:
                max_zysk = wynik_proc
                portfel["pozycje"][symbol]["max_zysk"] = max_zysk
                zapisz_json(PLIK_PORTFELA, portfel)

            # Ustalenie limitu wyświetlania
            limit_display = LIMITS["default"]
            if "jednodniowa" in typ_strat: limit_display = LIMITS["jednodniowa"]
            elif "tygodniowa" in typ_strat: limit_display = LIMITS["tygodniowa"]
            elif "4-godz" in typ_strat: limit_display = LIMITS["4-godzinna"]
            elif "godz" in typ_strat: limit_display = LIMITS["godzinowa"]
            elif "moonshot" in typ_strat: limit_display = LIMITS["moonshot"]

            # Logowanie stanu
            print(f"   📊 {symbol:<6} [{typ_strat}] | {'🟢' if wynik_proc > 0 else '🔴'} {wynik_proc:+.2f}% (Max:{max_zysk:.1f}%) | Czas: {format_czas(czas_trwania_min)}/{format_czas(limit_display)}")

            # =========================================================
            # 4. LOGIKA DECYZYJNA (3 ODDZIELNE ŚWIATY)
            # =========================================================
            
            decyzja_zamkniecia = False
            powod = ""

            # ---------------------------------------------------------
            # ŚWIAT 1: GODZINOWA (Szybki Skalp)
            # ---------------------------------------------------------
            if "godzinowa" in typ_strat:
                # Zasada 1: Take Profit (+1.5%)
                if wynik_proc >= 1.5:
                    decyzja_zamkniecia = True
                    powod = f"Take Profit (+{wynik_proc:.2f}%)"
                
                # Zasada 2: Stop Loss (-1.5%)
                elif wynik_proc <= -1.5:
                    decyzja_zamkniecia = True
                    powod = f"Stop Loss (-1.5%)"
                
                # Zasada 3: Koniec Czasu (60 min)
                elif czas_trwania_min >= LIMITS["godzinowa"]:
                    decyzja_zamkniecia = True
                    powod = f"Koniec Czasu (Limit 1h)"
                
                # Zasada 4: Break Even (Ochrona kapitału)
                elif max_zysk >= 0.8 and wynik_proc <= 0.1:
                    decyzja_zamkniecia = True
                    powod = "Break Even (Ochrona Kapitału)"

            # ---------------------------------------------------------
            # ŚWIAT 2: 4-GODZINNA (Swing Trading)
            # ---------------------------------------------------------
            elif "4-godz" in typ_strat:
                # Zasada 1: Take Profit (+4.0%)
                if wynik_proc >= 4.0:
                    decyzja_zamkniecia = True
                    powod = f"Take Profit (+{wynik_proc:.2f}%)"
                
                # Zasada 2: Stop Loss (-3.0%)
                elif wynik_proc <= -3.0:
                    decyzja_zamkniecia = True
                    powod = f"Stop Loss (-3.0%)"
                
                # Zasada 3: Trailing Stop (Ruchomy SL)
                # Jeśli zysk > 2.5%, podciągnij SL
                elif max_zysk >= 2.5 and wynik_proc < (max_zysk - 1.0):
                    decyzja_zamkniecia = True
                    powod = f"Trailing Stop (Zjazd z {max_zysk:.1f}%)"
                
                # Zasada 4: Break Even
                elif max_zysk >= 1.5 and wynik_proc <= 0.2:
                    decyzja_zamkniecia = True
                    powod = "Break Even (Ochrona Zysku)"
                
                # Zasada 5: Czas (4h)
                elif czas_trwania_min >= LIMITS["4-godzinna"]:
                    decyzja_zamkniecia = True
                    powod = f"Koniec Czasu (Limit 4h)"

            # ---------------------------------------------------------
            # ŚWIAT 3: JEDNODNIOWA (Inwestycja)
            # ---------------------------------------------------------
            elif "jednodniowa" in typ_strat:
                # Zasada 1: Take Profit (+8.0%)
                if wynik_proc >= 8.0:
                    decyzja_zamkniecia = True
                    powod = f"Take Profit (+{wynik_proc:.2f}%)"
                
                # Zasada 2: Stop Loss (-5.0%)
                elif wynik_proc <= -5.0:
                    decyzja_zamkniecia = True
                    powod = f"Stop Loss (-5.0%)"
                
                # Zasada 3: Trailing Stop (Luźny)
                elif max_zysk >= 5.0 and wynik_proc < (max_zysk - 2.0):
                    decyzja_zamkniecia = True
                    powod = f"Trailing Stop (Daily)"
                
                # Zasada 4: Break Even
                elif max_zysk >= 3.0 and wynik_proc <= 0.5:
                    decyzja_zamkniecia = True
                    powod = "Break Even (Daily)"
                
                # Zasada 5: Czas (25h)
                elif czas_trwania_min >= LIMITS["jednodniowa"]:
                    decyzja_zamkniecia = True
                    powod = f"Koniec Czasu (Limit 25h)"

            # ---------------------------------------------------------
            # 4. TYGODNIOWA (Long Term) - ULEPSZONA WERSJA
            # ---------------------------------------------------------
            elif "tygodniowa" in typ_strat:
                # 1. Take Profit (Celujemy wysoko, ale bez przesady)
                if wynik_proc >= 20.0: 
                    decyzja = True; powod = f"Take Profit (+{wynik_proc:.2f}%)"
                
                # 2. Stop Loss (Twardy, dla bezpieczeństwa)
                elif wynik_proc <= -8.0: 
                    decyzja = True; powod = f"Stop Loss (-8.0%)"
                
                # 3. Break Even (Ochrona kapitału)
                # Jak zarobimy +4%, podciągamy SL na +0.5% (żeby wyjść na zero z opłatami)
                elif max_zysk >= 4.0 and wynik_proc <= 0.5:
                    decyzja = True; powod = "Break Even (Weekly)"

                # 4. Trailing Stop (Inteligentny)
                # Jak zarobimy ponad +12%, pozwalamy cenie cofnąć się o max 4%
                # Daje to szansę na przetrwanie korekty, ale chroni duży zysk
                elif max_zysk >= 12.0 and wynik_proc < (max_zysk - 4.0):
                    decyzja = True; powod = f"Trailing Stop (Zjazd z {max_zysk:.1f}%)"
                
                # 5. Czas
                elif czas_trwania_min >= LIMITS["tygodniowa"]: 
                    decyzja = True; powod = "Koniec Czasu (7 dni)"

            # ---------------------------------------------------------
            # ŚWIAT 5: MOONSHOT (Pompa)
            # ---------------------------------------------------------
            elif "moonshot" in typ_strat:
                if max_zysk >= 10.0 and wynik_proc < (max_zysk - 3.0):
                    decyzja_zamkniecia = True; powod = "Trailing Moonshot"
                elif wynik_proc <= -4.0:
                    decyzja_zamkniecia = True; powod = "Stop Loss Moonshot"
                elif czas_trwania_min >= LIMITS["moonshot"]:
                    decyzja_zamkniecia = True; powod = "Koniec Czasu Moonshot"
            
            # Default fallback
            else:
                if wynik_proc >= 2.5: decyzja_zamkniecia = True; powod = "TP Default"
                elif wynik_proc <= -2.0: decyzja_zamkniecia = True; powod = "SL Default"
                elif czas_trwania_min >= 120: decyzja_zamkniecia = True; powod = "Timeout Default"

            # =========================================================
            # 6. EGZEKUCJA SPRZEDAŻY
            # =========================================================
            if decyzja_zamkniecia:
                print("="*50)
                print(f"   🔔 GŁÓWNY BOT: ZAMYKAM {symbol} [{typ_strat}]")
                
                akcja_str = "KONIEC CZASU" if "Koniec" in powod or "Limit" in powod else powod
                
                print(f"   📉 Akcja:        {akcja_str}")
                print(f"   ⏱️ Czas trwania: {format_czas(czas_trwania_min)}")
                print(f"   💵 Cena wejścia: {cena_wej:.4f}")
                print(f"   💵 Cena wyjścia: {cena_akt:.4f}")
                
                # Wywołanie managera
                zysk_usdt = pm.zwroc_srodki(symbol, cena_akt, zrodlo="MAIN_BOT")
                
                print(f"   💰 WYNIK:        ⌛ {wynik_proc:+.2f}% (Max: {max_zysk:.2f}%)")
                print(f"   📝 Powód:        {powod}")
                print(f"   🏦 PORTFEL:      {'🟢' if zysk_usdt > 0 else '🔴'} {zysk_usdt:+.2f} USDT")
                print("="*50)
                print("                                                         💾 Baza zaktualizowana natychmiast.")

        except Exception as e:
            # print(f"Błąd pozycji {symbol}: {e}") # Wyciszamy błędy pojedyncze
            continue

if __name__ == "__main__":
    main()
