import json
from datetime import datetime, timezone
import time
import random
import sys
import os
import statistics

# Import modułów
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from ai_helper import ask_ai
    from strategia_helper import save_strategies, extract_knowledge
    # ZMIANA: Importujemy nową funkcję budującą obraz rynku z bazy
    from utils_data import buduj_obraz_rynku_v2, calc_rsi
    from database_handler import DatabaseHandler # Nowy kolega
except ImportError as e:
    print(f"❌ Błąd importu w Mózgu: {e}")
    sys.exit()

# Łączymy się z bazą (Tylko do odczytu historii i aktywnych)
db = DatabaseHandler()

# Ścieżki do plików (Rynek nadal z pliku, bo to dane zewnętrzne)
RYNEK_PATH = "rynek.json"
MOZG_PATH = "mozg.json" # Plik komunikacyjny dla Schedulera (zostaje jako plik tymczasowy)
STRATEGIE_TEMP_PATH = "strategie.json" # Tymczasowe (debug)

def load_data(path):
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def save_brain(brain):
    try:
        with open(MOZG_PATH, "w", encoding="utf-8") as f: json.dump(brain, f, indent=2)
    except: pass

def przygotuj_historie():
    """
    Pobiera historię ostatnich transakcji Z BAZY DANYCH dla AI.
    Zastępuje czytanie z strategie_bota.json.
    """
    try:
        # Pobieramy ostatnie 5 transakcji z historii
        db.cursor.execute("SELECT symbol, typ_strategii, zysk_proc FROM historia_transakcji ORDER BY id DESC LIMIT 5")
        rows = db.cursor.fetchall()
        
        if not rows: return "Brak historii."
        
        raport = ""
        for r in rows:
            sym = r[0]
            typ = r[1]
            wynik = f"{r[2]:.2f}%"
            raport += f"- {sym} [{typ}]: {wynik}\n"
        return raport
    except Exception as e:
        return f"Błąd pobierania historii: {e}"

# =========================================================
# 🧠 INTELIGENTNY ALGORYTM V2 (Snajper + Wzrok SQL)
# =========================================================
def analiza_techniczna_zapasowa(typ, market_data, zablokowane_pary=[]):
    # Potrzebujemy importu tutaj, jeśli nie ma go na górze, ale zakładamy że jest w utils_data
    from utils_data import analizuj_dynamike_swiecy 
    
    kandydaci = []
    mapa_int = {"godzinowa": "1h", "4-godzinna": "4h", "jednodniowa": "1d", "tygodniowa": "1w"}
    interwal = mapa_int.get(typ, "1h")

    try:
        fng = int(market_data.get("sentiment", {}).get("value", 50))
    except: fng = 50

    limit_rsi_dip = 45
    min_vol_ratio = 1.0
    tryb = "NEUTRALNY"

    if fng <= 35: 
        tryb = "DEFENSYWNY (Strach)"
        limit_rsi_dip = 32
        min_vol_ratio = 1.2
    elif fng >= 60:
        tryb = "AGRESYWNY (Hossa)"
        limit_rsi_dip = 60
        min_vol_ratio = 0.8
        
    if "godz" in typ:
        limit_rsi_dip -= 4
        min_vol_ratio += 0.3

    for symbol, intervals in market_data.get("data", {}).items():
        symbol_usdt = symbol + "USDT"
        
        # 1. Sprawdź blokady
        if (symbol, typ) in zablokowane_pary or (symbol_usdt, typ) in zablokowane_pary:
            print(f"   ➤ [ALGO][{typ}] ⏭️ Pas {symbol}: AI już zajęło ten slot.")
            continue

        swiece = intervals.get(interwal, [])
        if not swiece or len(swiece) < 15: continue
        
        # Dane świecowe
        ceny = [s.get('c', s.get('close')) for s in swiece]
        volumeny = [s.get('v', s.get('vol')) for s in swiece]
        
        cena_akt = ceny[-1]
        rsi = calc_rsi(swiece)
        sma_20 = statistics.mean(ceny[-20:]) if len(ceny) >= 20 else statistics.mean(ceny)
        trend = "wzrost" if cena_akt > sma_20 else "spadek"
        
        avg_vol = statistics.mean(volumeny[-5:])
        vol_ratio = volumeny[-1] / avg_vol if avg_vol > 0 else 0
        
        # --- [NOWOŚĆ] WZROK BOTA (SQL + DYNAMIKA) ---
        dno_30d = db.znajdz_dno_historyczne(symbol, "1d", 30)
        odleglosc_od_dna = 100
        if dno_30d and dno_30d > 0:
            odleglosc_od_dna = ((cena_akt - dno_30d) / dno_30d) * 100
            
        ostatnia_swieca = swiece[-1]
        dynamika_opis = analizuj_dynamike_swiecy(ostatnia_swieca)
        
        # Bonus za bycie na dnie
        local_rsi_limit = limit_rsi_dip
        if odleglosc_od_dna < 5.0: # Jesteśmy na wsparciu!
            local_rsi_limit += 5 # Snajper jest odważniejszy
            tryb += " + WSPARCIE"

        odrzut = ""
        
        # FILTRY ODRZUCAJĄCE
        if vol_ratio < min_vol_ratio and not (rsi < 25): 
            odrzut = f"Słaby wolumen ({vol_ratio:.1f}x)"
        elif trend == "spadek" and rsi > local_rsi_limit:
             odrzut = f"Spadek + RSI {rsi:.1f} za wysokie"
        elif trend == "wzrost" and rsi >= 70:
             odrzut = f"Wykupione ({rsi:.1f})"
        
        # [NOWE FILTRY] Wzrok
        elif "Długi górny cień" in dynamika_opis:
            odrzut = f"Górny cień (Presja podaży)"
        elif odleglosc_od_dna > 50.0 and rsi > 60:
            odrzut = f"Wysoko od dna (+{odleglosc_od_dna:.0f}%) + RSI wysokie"

        if odrzut:
            print(f"   ➤ [ALGO][{typ}] 💤 Pas {symbol}: {odrzut}")
            continue

        is_candidate = False
        
        # Strategia A: DIP (Z uwzględnieniem Dna i Cieni)
        # Warunek: RSI nisko LUB (Jesteśmy na dnie I mamy dolny cień)
        warunek_dna = (odleglosc_od_dna < 3.0 and "Długi dolny cień" in dynamika_opis)
        
        if rsi <= local_rsi_limit or warunek_dna:
            powod = f"DIP ({tryb}) RSI {rsi:.1f}"
            if warunek_dna: powod += " + ODBICIE OD DNA 🔥"
            
            kandydaci.append({
                "nazwa": f"{symbol}_SmartDip", "symbol": symbol, "typ": typ,
                "warunek": powod,
                "oczekiwany_ruch": "wzrost", "pewnosc": "średnia"
            })
            is_candidate = True
            
        # Strategia B: TREND
        elif trend == "wzrost" and fng > 40 and rsi < 65:
            # Nie wchodzimy w trend, jeśli świeca jest brzydka (Doji/Górny cień)
            if "Doji" not in dynamika_opis:
                kandydaci.append({
                    "nazwa": f"{symbol}_TrendRide", "symbol": symbol, "typ": typ,
                    "warunek": f"TREND ({tryb}) RSI {rsi:.1f} + Vol {vol_ratio:.1f}x",
                    "oczekiwany_ruch": "wzrost", "pewnosc": "wysoka"
                })
                is_candidate = True
            
        if not is_candidate:
            print(f"   ➤ [ALGO][{typ}] 💤 Pas {symbol}: Brak sygnału")

    if kandydaci:
        if fng < 40:
            kandydaci.sort(key=lambda x: 3 if x['symbol'] == 'BTC' else (2 if x['symbol'] == 'ETH' else 1), reverse=True)
        wybor = random.choice(kandydaci)
        print(f"   ➤ [ALGO][{typ}] 🎯 CEL ({tryb}): {wybor['symbol']} ({wybor['warunek']})")
        return [wybor]
    
    return []

def generuj_raport_4_slotowy(obraz, historia, sentyment_str, sentyment_wartosc, dostepne_coiny):
    # --- PROMPT DLA AI Z AKTUALIZACJĄ O WZROK ---
    lista_coinow_str = ", ".join(dostepne_coiny)

    prompt = f"""
    Jesteś Senior Traderem AI z 20-letnim doświadczeniem w krypto.
    Twoim celem jest ZYSKOWNY HANDEL SWINGOWY, a nie hazard.
    
    === SYTUACJA RYNKOWA ===
    Globalny Sentyment: {sentyment_str} (Index: {sentyment_wartosc}/100)
    DOSTĘPNE MONETY DO ANALIZY: {lista_coinow_str}
    HISTORIA TRANSAKCJI (Twoje wyniki):
    {historia}
    
    === DANE DO ANALIZY (WZROK BOTA) ===
    Otrzymujesz dane o:
    1. Pozycji ceny względem 30-dniowego DNA (Wsparcie z bazy danych).
    2. Dynamice świec (Kształt, Cienie, Siła).
    
    {obraz}
    
    === TWOJA STRATEGIA (INTELIGENCJA) ===
    1. FILTR BITCOINA (Najważniejsze):
       - Jeśli BTC spada dynamicznie -> ODRZUCAJ WSZYSTKIE ALTCOINY (Risk Off).
       - Jeśli BTC jest stabilny lub rośnie -> Szukaj okazji (Risk On).
       
    2. ANALIZA TECHNICZNA (Szukaj Konfluencji):
       - RSI < 30 + Extreme Fear: Okazja na odbicie.
       - RSI > 70 + Greed: Ryzyko korekty. Nie kupuj, chyba że to wybicie na wolumenie.
       - Volume Ratio: < 0.5 unikać (martwy rynek), > 2.0 obserwować (pompa).
       - DNO Z BAZY: Jeśli cena jest blisko 30-dniowego dołka (+0-5%) -> SZUKAJ WEJŚCIA.
       - DYNAMIKA: Jeśli widzisz długi dolny cień (Pinbar) na wsparciu -> SILNY SYGNAŁ KUPNA.
       - DYNAMIKA: Jeśli widzisz długi górny cień na oporze -> UNIKAJ.
       
    3. KONSEKWENCJA:
       - Nie "zgaduj". Jeśli nie ma czystego sygnału -> Decyzja: NIE.
       - Lepiej stracić okazję niż stracić kapitał.

    === FORMAT ODPOWIEDZI (WYMAGANY) ===
    Musisz zwrócić WYŁĄCZNIE poprawny kod JSON będący LISTĄ obiektów.
    Przeanalizuj WSZYSTKIE monety z listy: {lista_coinow_str}. Nie pomijaj żadnej.
    Używaj tylko nazw typów: 'godzinowa', '4-godzinna', 'jednodniowa', 'tygodniowa'.
    
    === TWOJE ZADANIE (BARDZO WAŻNE) ===
    Musisz przeanalizować KAŻDĄ monetę ({lista_coinow_str}) pod kątem KAŻDEGO z 4 horyzontów czasowych:
    1. 'godzinowa'
    2. '4-godzinna'
    3. 'jednodniowa'
    4. 'tygodniowa'
    
    To oznacza, że jeśli masz 4 monety, musisz zwrócić dokładnie 16 obiektów JSON.
    Dla każdego obiektu zdecyduj: "TAK" (Kupuj) lub "NIE" (Czekaj).
    
    FORMAT ODPOWIEDZI (LISTA JSON):
    [
        {{ "symbol": "BTC", "typ": "godzinowa", "decyzja": "NIE", "warunek": "Zbyt niski wolumen" }},
        {{ "symbol": "BTC", "typ": "4-godzinna", "decyzja": "NIE", "warunek": "RSI neutralne" }},
        {{ "symbol": "BTC", "typ": "jednodniowa", "decyzja": "TAK", "warunek": "Trend wzrostowy potwierdzony" }},
        {{ "symbol": "BTC", "typ": "tygodniowa", "decyzja": "TAK", "warunek": "Długoterminowa akumulacja" }},
        {{ "symbol": "ETH", "typ": "godzinowa", "decyzja": "NIE", "warunek": "..." }}
        ... (i tak dalej dla wszystkich monet i typów)
    ]
    """
    return ask_ai(prompt)

def wybierz_najlepsza_strategie(kandydaci):
    """
    Wybiera najlepszą strategię, sprawdzając zajęte sloty W BAZIE SQL.
    """
    if not kandydaci: return None

    # Zbieranie zajętych slotów Z BAZY
    try:
        db.cursor.execute("SELECT unikalne_id FROM aktywne_pozycje")
        zajete_sloty = set([row[0] for row in db.cursor.fetchall()])
    except:
        zajete_sloty = set()

    # Filtrowanie
    wolni_kandydaci = []
    for k in kandydaci:
        unikalne_id = f"{k['symbol']}_{k['typ']}"
        if unikalne_id in zajete_sloty:
            print(f"   ⚠️ Pomijam {k['symbol']} [{k['typ']}] - ten slot jest zajęty.")
            continue
        wolni_kandydaci.append(k)

    if not wolni_kandydaci: return None

    # Sortowanie wg pewności i priorytetu
    priorytety = { "godzinowa": 1, "4-godzinna": 2, "jednodniowa": 3, "dzienna": 3, "tygodniowa": 4 }
    wolni_kandydaci.sort(key=lambda x: (
        0 if x.get("pewnosc") == "wysoka" else 1, 
        priorytety.get(x["typ"], 99)
    ))

    return wolni_kandydaci[0]

def main():
    market = load_data(RYNEK_PATH)
    if not market.get("data"): return

    print(f"\n==================================================")
    print(f"🧠 MÓZG BOTA: START ANALIZY ({datetime.now().strftime('%H:%M')})")
    print(f"==================================================")

    godzina = datetime.now().hour
    tryb_tylko_algo = False
    
    if 18 <= godzina < 23:
        tryb_tylko_algo = True
        print(f"🌙 TRYB NOCNY (SIESTA 18-23). AI odpoczywa.")
    else:
        print(f"☀️ TRYB DZIENNY. AI i Algorytm współpracują.")

    fng = market.get("sentiment", {})
    sentyment_val = fng.get('value', 50)
    sentyment_klasa = fng.get('value_classification', 'Neutral')
    print(f"🎭 Rynek: Sentyment {sentyment_val} ({sentyment_klasa})")
    
    finalne_strategie = []
    zablokowane_pary_tak = [] 

    # --- SEKCJA AI ---
    if not tryb_tylko_algo:
        print("-" * 50)
        print(f"🤖 [1] KONSULTACJA AI (Gemini + Wzrok SQL):")
        
        obraz_rynku = ""
        dostepne_coiny = list(market["data"].keys())
        
        for sym in dostepne_coiny:
            # ZMIANA: Używamy nowej funkcji budującej obraz z bazy (Wzrok)
            # Przekazujemy 'db' jako uchwyt do bazy
            symbol_data = market["data"][sym]
            obraz_rynku += buduj_obraz_rynku_v2(sym, symbol_data, db)

        try:
            # Historia teraz idzie z SQL przez funkcję przygotuj_historie()
            resp = generuj_raport_4_slotowy(obraz_rynku, przygotuj_historie(), sentyment_klasa, sentyment_val, dostepne_coiny)
            
            if resp:
                raport, msg = extract_knowledge(resp)
                if raport:
                    if isinstance(raport, list):
                        for pozycja in raport:
                            if not isinstance(pozycja, dict): continue

                            typ = pozycja.get("typ", "nieznany")
                            decyzja = pozycja.get("decyzja", "NIE")
                            sym = pozycja.get("symbol", "NIEZNANY")
                            warunek = pozycja.get("warunek", "Brak powodu")

                            sym_short = sym.replace("USDT", "")

                            ikona = "✅" if decyzja == "TAK" else "❌"
                            print(f"   {ikona} {decyzja} [{typ}]: {sym} -> {warunek}")

                            if decyzja == "TAK":
                                s = {
                                    "nazwa": f"{sym}_AI_{typ}", "symbol": sym, "typ": typ,
                                    "warunek": warunek, "oczekiwany_ruch": "wzrost", 
                                    "pewnosc": "wysoka", "zrodlo": "AI"
                                }
                                finalne_strategie.append(s)
                                
                                zablokowane_pary_tak.append((sym, typ))
                                zablokowane_pary_tak.append((sym_short, typ))
                    else:
                        print(f"   ⚠️ Otrzymano zły format od AI (oczekiwano listy).")
                else:
                    print(f"   ⚠️ Błąd parsowania odpowiedzi AI: {msg}")

        except Exception as e:
            print(f"   ⚠️ Błąd AI (Critical): {e}")

    # --- SEKCJA ALGORYTMU (SNAJPER) ---
    print("-" * 50)
    print(f"🛡️ [2] WERYFIKACJA MATEMATYCZNA (Snajper):")
    
    typy_wszystkie = ["godzinowa", "4-godzinna", "jednodniowa", "tygodniowa"]

    for typ in typy_wszystkie:
        awaryjne = analiza_techniczna_zapasowa(typ, market, zablokowane_pary_tak)
        if awaryjne:
            awaryjne[0]['zrodlo'] = f"Algorytm ({sentyment_klasa})"
            finalne_strategie.extend(awaryjne)

    # --- FINALE ---
    print("=" * 50)
    if finalne_strategie:
        print(f"🚀 SUKCES! Znaleziono {len(finalne_strategie)} kandydatów.")
        save_strategies(finalne_strategie)
        
        # Wybieranie najlepszej (Teraz sprawdza sloty w SQL)
        wybrana = wybierz_najlepsza_strategie(finalne_strategie)
        
        if wybrana:
            decyzja_dla_schedulera = {
                "akcja": "KUP", 
                "symbol": wybrana["symbol"],
                "typ_strategii": wybrana["typ"], # Kluczowe dla Schedulera
                "zrodlo": wybrana.get("zrodlo", "Algorytm"),
                "uzasadnienie": wybrana["warunek"],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            save_brain(decyzja_dla_schedulera)
            print(f"🧠 [CONNECT] Wybrano do realizacji: {wybrana['symbol']} [{wybrana['typ']}]")
        else:
            print("🧠 [CONNECT] Brak nowych unikalnych strategii (wszystkie sloty zajęte).")
            save_brain({"akcja": "CZEKAJ", "powod": "Dublowanie strategii"})

    else:
        print("💤 PUSTO. Cierpliwość to klucz.")
        save_brain({"akcja": "CZEKAJ", "powod": "Brak strategii"})
        try:
            with open(STRATEGIE_TEMP_PATH, "w", encoding="utf-8") as f: json.dump([], f)
        except: pass

if __name__ == "__main__":
    main()