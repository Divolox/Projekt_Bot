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
    from utils_data import buduj_obraz_rynku_v2, calc_rsi, analizuj_dynamike_swiecy 
    from database_handler import DatabaseHandler
except ImportError as e:
    print(f"❌ Błąd importu w Mózgu: {e}")
    sys.exit()

db = DatabaseHandler()

RYNEK_PATH = "rynek.json"
MOZG_PATH = "mozg.json" 
STRATEGIE_TEMP_PATH = "strategie.json"

def load_data(path):
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def save_brain(brain):
    try:
        with open(MOZG_PATH, "w", encoding="utf-8") as f: json.dump(brain, f, indent=2)
    except: pass

def przygotuj_historie():
    try:
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
# 🧠 INTELIGENTNY ALGORYTM V3.1 (SENTYMENT 5-STREF + TREND RIDE + DNA RESTORED)
# =========================================================
def analiza_techniczna_zapasowa(typ, market_data, zablokowane_pary=[]):
    # --- FILTR DLA ALGORYTMU ---
    # Jeśli typ strategii to 'jednodniowa' lub 'tygodniowa',
    # to Snajper ma analizować TYLKO BTC i ETH (oraz SOL/XRP).
    wymagani_krolowie = ["BTC", "ETH", "SOL", "XRP", "XRPUSDT", "SOLUSDT", "BTCUSDT", "ETHUSDT"]

    kandydaci = []
    mapa_int = {"godzinowa": "1h", "4-godzinna": "4h", "jednodniowa": "1d", "tygodniowa": "1w"}
    interwal = mapa_int.get(typ, "1h")

    # --- ROZBUDOWANA LOGIKA SENTYMENTU (5 STREF) ---
    try:
        fng = int(market_data.get("sentiment", {}).get("value", 50))
    except: fng = 50

    # Parametry bazowe
    limit_rsi_dip = 45      # Poniżej tego kupujemy (DIP)
    min_vol_ratio = 1.0     # Wymagany wolumen względem średniej
    tryb = "NEUTRALNY"
    
    # 1. EXTREME FEAR (0-25)
    if fng <= 25:
        tryb = "EXTREME FEAR (Krew)"
        limit_rsi_dip = 28
        min_vol_ratio = 1.5
    
    # 2. FEAR (26-45)
    elif fng <= 45:
        tryb = "FEAR (Ostrożnie)"
        limit_rsi_dip = 38
        min_vol_ratio = 1.2
    
    # 3. NEUTRAL (46-54)
    elif fng < 55:
        tryb = "NEUTRAL"
        limit_rsi_dip = 45
        min_vol_ratio = 1.0

    # 4. GREED (55-75)
    elif fng <= 75:
        tryb = "GREED (Momentum)"
        limit_rsi_dip = 55
        min_vol_ratio = 1.5

    # 5. EXTREME GREED (>75)
    else:
        tryb = "EXTREME GREED (Ryzyko)"
        limit_rsi_dip = 60
        min_vol_ratio = 2.0

    # Korekta dla krótkich interwałów
    if "godz" in typ:
        limit_rsi_dip -= 3
        if fng > 75: limit_rsi_dip = 65 

    for symbol, intervals in market_data.get("data", {}).items():
        symbol_usdt = symbol + "USDT"
        
        # --- BLOKADA ALTÓW NA DŁUGIM TERMINIE ---
        if typ in ["jednodniowa", "tygodniowa"]:
            if symbol not in wymagani_krolowie and symbol_usdt not in wymagani_krolowie:
                continue
        # ----------------------------------------

        if (symbol, typ) in zablokowane_pary or (symbol_usdt, typ) in zablokowane_pary:
            # print(f"   ➤ [ALGO][{typ}] ⏭️ Pas {symbol}: AI już zajęło ten slot.")
            continue

        swiece = intervals.get(interwal, [])
        if not swiece or len(swiece) < 15: continue
        
        ceny = [s.get('c', s.get('close')) for s in swiece]
        volumeny = [s.get('v', s.get('vol')) for s in swiece]
        
        cena_akt = ceny[-1]
        rsi = calc_rsi(swiece)
        
        sma_20 = statistics.mean(ceny[-20:]) if len(ceny) >= 20 else statistics.mean(ceny)
        trend = "wzrost" if cena_akt > sma_20 else "spadek"
        
        avg_vol = statistics.mean(volumeny[-5:])
        vol_ratio = volumeny[-1] / avg_vol if avg_vol > 0 else 0
        
        # Wzrok SQL
        dno_30d = db.znajdz_dno_historyczne(symbol, "1d", 30)
        odleglosc_od_dna = 100
        if dno_30d and dno_30d > 0:
            odleglosc_od_dna = ((cena_akt - dno_30d) / dno_30d) * 100
            
        ostatnia_swieca = swiece[-1]
        dynamika_opis = analizuj_dynamike_swiecy(ostatnia_swieca)
        
        # Logika DNA (Wsparcie)
        local_rsi_limit = limit_rsi_dip
        if odleglosc_od_dna < 5.0: 
            local_rsi_limit += 7
            tryb += " + DNO"

        odrzut = ""
        # Filtry odrzucające (Oryginalne zachowane)
        if vol_ratio < min_vol_ratio and not (rsi < 25): 
            odrzut = f"Słaby wolumen ({vol_ratio:.1f}x)"
        elif trend == "spadek" and rsi > local_rsi_limit:
             odrzut = f"Spadek + RSI {rsi:.1f} za wysokie"
        elif trend == "wzrost" and rsi >= 70:
             odrzut = f"Wykupione ({rsi:.1f})"
        elif "Długi górny cień" in dynamika_opis:
            odrzut = f"Górny cień (Presja podaży)"
        elif odleglosc_od_dna > 50.0 and rsi > 60:
            odrzut = f"Wysoko od dna (+{odleglosc_od_dna:.0f}%) + RSI wysokie"

        if odrzut:
            print(f"   ➤ [ALGO][{typ}] 💤 Pas {symbol}: {odrzut}")
            continue

        is_candidate = False
        
        # --- [PRZYWRÓCONE] STRATEGIA 1: DNA / DIP ---
        # Pinbar blisko dna to sygnał niezależnie od wszystkiego
        warunek_dna = (odleglosc_od_dna < 3.0 and "Długi dolny cień" in dynamika_opis)
        
        if rsi <= local_rsi_limit or warunek_dna:
            powod = f"DIP ({tryb}) RSI {rsi:.1f}"
            if warunek_dna: powod += " + ODBICIE OD DNA"
            
            # W Extreme Fear tylko Królowie lub super okazje
            if fng <= 25 and not warunek_dna and symbol not in wymagani_krolowie:
                pass # W panice alty kupujemy tylko na pinbarze (warunek_dna), nie na samym RSI
            else:
                kandydaci.append({
                    "nazwa": f"{symbol}_SmartDip", "symbol": symbol, "typ": typ,
                    "warunek": powod,
                    "oczekiwany_ruch": "wzrost", "pewnosc": "średnia"
                })
                is_candidate = True
        
        # --- [PRZYWRÓCONE] STRATEGIA 2: TREND RIDE ---
        # Działa tylko jeśli sentyment jest lepszy niż Extreme Fear (>25)
        elif trend == "wzrost" and fng > 25 and rsi < 65:
            if "Doji" not in dynamika_opis:
                # Wymagany wolumen potwierdza siłę trendu
                if vol_ratio >= min_vol_ratio:
                    kandydaci.append({
                        "nazwa": f"{symbol}_TrendRide", "symbol": symbol, "typ": typ,
                        "warunek": f"TREND ({tryb}) RSI {rsi:.1f} + Vol {vol_ratio:.1f}x",
                        "oczekiwany_ruch": "wzrost", "pewnosc": "wysoka"
                    })
                    is_candidate = True
            
        if not is_candidate:
            print(f"   ➤ [ALGO][{typ}] 💤 Pas {symbol}: Brak sygnału")

    if kandydaci:
        # W Extreme Fear priorytet mają BTC/ETH
        if fng < 30:
            kandydaci.sort(key=lambda x: 3 if 'BTC' in x['symbol'] else (2 if 'ETH' in x['symbol'] else 1), reverse=True)
        
        wybor = random.choice(kandydaci)
        print(f"   ➤ [ALGO][{typ}] 🎯 CEL ({tryb}): {wybor['symbol']} ({wybor['warunek']})")
        return [wybor]
    
    return []

def generuj_raport_4_slotowy(obraz, historia, sentyment_str, sentyment_wartosc, dostepne_coiny):
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

    Jedynymi wyjątkami dla których musisz wymyślić tylko godzinowa oraz 4-godzinowa są :
    1.BNBUSDT
    2.DOGEUSDT
    3.ADAUSDT
    4.LINKUSDT
    5.AVAXUSDT
    DLA 'jednodniowa' i 'tygodniowa' dla tych coinow wpisz automatycznie decyzję: "NIE" (Powód: "Zbyt duże ryzyko dla Alta").
    
    Dla każdego obiektu zdecyduj: "TAK" (Kupuj) lub "NIE" (Czekaj).
    
    FORMAT ODPOWIEDZI (LISTA JSON):
    [
        {{ "symbol": "BTC", "typ": "godzinowa", "decyzja": "NIE", "warunek": "Zbyt niski wolumen" }},
        {{ "symbol": "BTC", "typ": "4-godzinna", "decyzja": "NIE", "warunek": "RSI neutralne" }},
        {{ "symbol": "BTC", "typ": "jednodniowa", "decyzja": "TAK", "warunek": "Trend wzrostowy potwierdzony" }},
        {{ "symbol": "BTC", "typ": "tygodniowa", "decyzja": "TAK", "warunek": "Długoterminowa akumulacja" }},
        {{ "symbol": "ETH", "typ": "godzinowa", "decyzja": "NIE", "warunek": "..." }}
        ... (i tak dalej dla wszystkich monet i typów, oprócz tych wybranych 5 dla których musisz podać tylko godzinowa i 4-godzinowa)
    ]
    """
    return ask_ai(prompt)

def wybierz_najlepsza_strategie(kandydaci):
    """
    Wybiera najlepszą strategię, z ABSOLUTNYM PRIORYTETEM DLA AI.
    """
    if not kandydaci: return None

    # Zbieranie zajętych slotów
    try:
        db.cursor.execute("SELECT unikalne_id FROM aktywne_pozycje")
        zajete_sloty = set([row[0] for row in db.cursor.fetchall()])
    except:
        zajete_sloty = set()

    wolni_kandydaci = []
    for k in kandydaci:
        unikalne_id = f"{k['symbol']}_{k['typ']}"
        if unikalne_id in zajete_sloty:
            print(f"   ⚠️ Pomijam {k['symbol']} [{k['typ']}] - ten slot jest zajęty.")
            continue
        wolni_kandydaci.append(k)

    if not wolni_kandydaci: return None

    # === TUTAJ JEST ZMIANA PRIORYTETÓW ===
    # 1. Priorytet Źródła (AI = 0, Algorytm = 1) -> AI ZAWSZE WYGRA
    # 2. Priorytet Pewności (wysoka = 0, inna = 1)
    # 3. Priorytet Czasu (krótszy czas = szybki zysk)
    
    priorytety_czasu = { "godzinowa": 1, "4-godzinna": 2, "jednodniowa": 3, "dzienna": 3, "tygodniowa": 4 }
    
    wolni_kandydaci.sort(key=lambda x: (
        0 if x.get("zrodlo") == "AI" else 1,    # <--- TO JEST KLUCZ! AI ma 0, Algo ma 1.
        0 if x.get("pewnosc") == "wysoka" else 1, 
        priorytety_czasu.get(x["typ"], 99)
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
            symbol_data = market["data"][sym]
            obraz_rynku += buduj_obraz_rynku_v2(sym, symbol_data, db)

        try:
            resp = generuj_raport_4_slotowy(obraz_rynku, przygotuj_historie(), sentyment_klasa, sentyment_val, dostepne_coiny)
            
            if resp:
                raport, msg = extract_knowledge(resp)
                if raport and isinstance(raport, list):
                        for pozycja in raport:
                            if not isinstance(pozycja, dict): continue

                            typ = pozycja.get("typ", "nieznany")
                            decyzja = pozycja.get("decyzja", "NIE")
                            sym = pozycja.get("symbol", "NIEZNANY")
                            warunek = pozycja.get("warunek", "Brak powodu")
                            sym_short = sym.replace("USDT", "")

                            # --- FILTR ALTCOINÓW (TWOJE ŻYCZENIE) ---
                            # Definicja Królów, którzy mogą mieć długie strategie
                            krolowie = ["BTC", "ETH", "SOL", "XRP", "XRPUSDT", "SOLUSDT", "BTCUSDT", "ETHUSDT"] 
                            
                            # Jeśli to nie król, a strategia jest długa -> WYJAZD
                            if sym not in krolowie and typ in ["jednodniowa", "tygodniowa"]:
                                # Możesz to odkomentować, jak chcesz widzieć w logach, że odrzucił
                                # print(f"   🚫 [FILTR] Odrzucono {sym} [{typ}] - Alty tylko 1h/4h.")
                                continue
                            # ----------------------------------------

                            ikona = "✅" if decyzja == "TAK" else "❌"
                            print(f"   {ikona} {decyzja} [{typ}]: {sym} -> {warunek}")

                            if decyzja == "TAK":
                                s = {
                                    "nazwa": f"{sym}_AI_{typ}", "symbol": sym, "typ": typ,
                                    "warunek": warunek, "oczekiwany_ruch": "wzrost", 
                                    "pewnosc": "wysoka", "zrodlo": "AI"  # <--- WAŻNE OZNACZENIE
                                }
                                finalne_strategie.append(s)
                                zablokowane_pary_tak.append((sym, typ))
                                zablokowane_pary_tak.append((sym_short, typ))
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
            awaryjne[0]['zrodlo'] = f"Algorytm ({sentyment_klasa})" # <--- Inne źródło
            finalne_strategie.extend(awaryjne)

    # --- FINALE ---
    print("=" * 50)
    if finalne_strategie:
        print(f"🚀 SUKCES! Znaleziono {len(finalne_strategie)} kandydatów.")
        save_strategies(finalne_strategie)
        
        # Wybieranie najlepszej (Teraz z PRIORYTETEM AI)
        wybrana = wybierz_najlepsza_strategie(finalne_strategie)
        
        if wybrana:
            decyzja_dla_schedulera = {
                "akcja": "KUP", 
                "symbol": wybrana["symbol"],
                "typ_strategii": wybrana["typ"], 
                "zrodlo": wybrana.get("zrodlo", "Algorytm"),
                "uzasadnienie": wybrana["warunek"],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            save_brain(decyzja_dla_schedulera)
            print(f"🧠 [CONNECT] Wybrano do realizacji: {wybrana['symbol']} [{wybrana['typ']}] (Źródło: {wybrana.get('zrodlo')})")
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

