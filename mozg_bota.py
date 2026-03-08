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
    from utils_data import buduj_obraz_rynku_v2, calc_rsi, analizuj_dynamike_swiecy, okresl_strukture_rynku, znajdz_wsparcia_i_opory
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
# 👻 WERYFIKACJA W BAZIE DOŚWIADCZEŃ (DUCHY)
# =========================================================
def weryfikuj_przez_duchy(kandydat, market_data, db_handler):
    """
    Sprawdza, czy w przeszłości w podobnym układzie rynek wyjebał nas, czy dał zarobić.
    Zwraca: (Status, Szansa_Procentowa)
    """
    symbol = kandydat['symbol']
    sym_short = symbol.replace("USDT", "")
    swiece = market_data.get("data", {}).get(sym_short, {}).get("1h", [])
    if not swiece: swiece = market_data.get("data", {}).get(symbol, {}).get("1h", [])
    
    if not swiece or len(swiece) < 20: return "BRAK", 50.0
    
    cena_akt = float(swiece[-1].get('c', swiece[-1].get('close', 0)))
    rsi = calc_rsi(swiece)
    struktura = okresl_strukture_rynku(swiece)
    wsparcie, _ = znajdz_wsparcia_i_opory(swiece, cena_akt)
    
    dyst_wsp = ((cena_akt - wsparcie) / wsparcie * 100) if wsparcie else 0.0
    
    try: sentyment_val = int(market_data.get("sentiment", {}).get("value", 50))
    except: sentyment_val = 50
    
    # Patrzymy na podobny rynek (sentyment)
    db_handler.cursor.execute('''
        SELECT struktura_wykresu, dystans_wsparcie, rsi, decyzja, ocena_ducha
        FROM wzorce_rynkowe 
        WHERE sentyment >= ? AND sentyment <= ? AND ocena_ducha != -1
        ORDER BY id DESC LIMIT 300
    ''', (sentyment_val - 15, sentyment_val + 15))
    
    historia = db_handler.cursor.fetchall()
    if not historia: return "BRAK", 50.0 # Jeśli nie ma danych, ufa swojemu instynktowi
    
    podobne = []
    for w in historia:
        w_struktura, w_wsp, w_rsi, w_decyzja, w_ocena = w
        punkty = 0
        
        # Płynne podobieństwo (kontekst)
        if str(w_struktura).split(' ')[0] in struktura: punkty += 40
        if abs(dyst_wsp - float(w_wsp)) <= 2.0: punkty += 40
        if abs(rsi - float(w_rsi)) <= 15: punkty += 20
        
        if punkty >= 70: # Sytuacja uznana za "Taki sam klimat"
            dobry_zakup = 0
            if w_decyzja == "TP": dobry_zakup = 1
            elif w_ocena == 0: dobry_zakup = 1 # Jeśli wyszliśmy za wcześnie (błąd ducha), to znaczy że opłacało się wejść/trzymać
            
            podobne.append(dobry_zakup)
            
    if len(podobne) < 3: return "BRAK", 50.0 
    
    szansa = (sum(podobne) / len(podobne)) * 100
    return "ZNANE", szansa

# =========================================================
# 🧠 INTELIGENTNY ALGORYTM V4.0 (PŁYNNE CZYTANIE RYNKU)
# =========================================================
def analiza_techniczna_zapasowa(typ, market_data, zablokowane_pary=[]):
    # --- FILTR DLA ALGORYTMU ---
    # Jeśli typ strategii to 'jednodniowa' lub 'tygodniowa',
    # to Snajper ma analizować TYLKO BTC i ETH (oraz SOL/XRP).
    wymagani_krolowie = ["BTC", "ETH", "SOL", "XRP", "XRPUSDT", "SOLUSDT", "BTCUSDT", "ETHUSDT"]

    kandydaci = []
    mapa_int = {"godzinowa": "1h", "4-godzinna": "4h", "jednodniowa": "1d", "tygodniowa": "1w"}
    interwal = mapa_int.get(typ, "1h")

    try:
        fng = int(market_data.get("sentiment", {}).get("value", 50))
    except: fng = 50

    tryb = "NEUTRALNY"
    if fng <= 25: tryb = "EXTREME FEAR (Krew)"
    elif fng <= 45: tryb = "FEAR (Ostrożnie)"
    elif fng < 55: tryb = "NEUTRAL"
    elif fng <= 75: tryb = "GREED (Momentum)"
    else: tryb = "EXTREME GREED (Ryzyko)"

    for symbol, intervals in market_data.get("data", {}).items():
        symbol_usdt = symbol + "USDT"
        
        # --- BLOKADA ALTÓW NA DŁUGIM TERMINIE ---
        if typ in ["jednodniowa", "tygodniowa"]:
            if symbol not in wymagani_krolowie and symbol_usdt not in wymagani_krolowie:
                continue
        # ----------------------------------------

        if (symbol, typ) in zablokowane_pary or (symbol_usdt, typ) in zablokowane_pary:
            continue

        swiece = intervals.get(interwal, [])
        if not swiece or len(swiece) < 20: continue
        
        ceny = [float(s.get('c', s.get('close', 0))) for s in swiece]
        volumeny = [float(s.get('v', s.get('vol', 0))) for s in swiece]
        
        cena_akt = ceny[-1]
        rsi = calc_rsi(swiece)
        
        sma_20 = statistics.mean(ceny[-20:]) if len(ceny) >= 20 else statistics.mean(ceny)
        trend = "wzrost" if cena_akt > sma_20 else "spadek"
        
        avg_vol = statistics.mean(volumeny[-5:])
        vol_ratio = volumeny[-1] / avg_vol if avg_vol > 0 else 0
        
        # Oczy bota (Zmysł przestrzenny)
        struktura = okresl_strukture_rynku(swiece)
        wsparcie, opor = znajdz_wsparcia_i_opory(swiece, cena_akt)
        
        dyst_wsp = ((cena_akt - wsparcie) / wsparcie * 100) if wsparcie else 100.0
        dyst_opor = ((opor - cena_akt) / cena_akt * 100) if opor else 100.0
        
        ostatnia_swieca = swiece[-1]
        dynamika_opis = analizuj_dynamike_swiecy(ostatnia_swieca)

        odrzut = ""
        is_candidate = False

        # ========================================================
        # 🧠 PŁYNNE MYŚLENIE KONTEKSTOWE (Zamiast sztywnych limitów)
        # ========================================================
        
        # KONTEKST 1: KREW NA ULICACH (Extreme Fear)
        if fng <= 25:
            # Ludzie srają ze strachu. Jak leci nóż (Struktura Niedźwiedzia i brak podłogi), to nie łapiemy.
            if "Niedźwiedzia" in struktura and dyst_wsp > 3.0:
                odrzut = f"Lecący nóż (Brak wsparcia w zasięgu wzroku)"
            # Ale jak jest na wsparciu (DNO) i robi się pinbar, to jest to złoto.
            elif dyst_wsp <= 2.0 and ("dolny cień" in dynamika_opis or rsi < 30):
                powod = f"INTELIGENTNE ODBICIE (Wsparcie: -{dyst_wsp:.1f}%, RSI: {rsi:.1f})"
                is_candidate = True
            else:
                odrzut = "Brak czytelnego sygnału na panikę"

        # KONTEKST 2: HOSSA I CHCIWOŚĆ (Greed / Extreme Greed)
        elif fng > 55:
            # W hossie kupujemy siłę.
            if "Niedźwiedzia" in struktura:
                odrzut = "Rynek rośnie, a to jest trup (Struktura spadkowa)"
            elif trend == "wzrost" and vol_ratio > 1.2 and dyst_opor > 2.0:
                powod = f"RIDE THE WAVE (Czysta droga do oporu: +{dyst_opor:.1f}%, Vol: {vol_ratio:.1f}x)"
                is_candidate = True
            else:
                odrzut = "Brak momentum"

        # KONTEKST 3: NEUTRALNY RYNEK (Czysta Analiza Techniczna)
        else:
            if dyst_opor < 1.0:
                odrzut = f"Za blisko sufitu (+{dyst_opor:.1f}%)"
            elif rsi < 35 and "Bycza" in struktura:
                powod = f"Techniczny dołek w trendzie (RSI: {rsi:.1f})"
                is_candidate = True
            elif dyst_wsp <= 1.5 and vol_ratio > 1.0:
                powod = f"Obrona poziomu (Wsparcie: -{dyst_wsp:.1f}%)"
                is_candidate = True
            else:
                odrzut = "Konsolidacja bez krawędzi"

        if odrzut:
            print(f"   ➤ [ALGO][{typ}] 💤 Pas {symbol}: {odrzut}")
            continue

        if is_candidate:
            kandydaci.append({
                "nazwa": f"{symbol}_SmartLogic", "symbol": symbol, "typ": typ,
                "warunek": powod,
                "oczekiwany_ruch": "wzrost", "pewnosc": "wysoka"
            })

    if kandydaci:
        if fng < 30:
            kandydaci.sort(key=lambda x: 3 if 'BTC' in x['symbol'] else (2 if 'ETH' in x['symbol'] else 1), reverse=True)
        
        wybor = random.choice(kandydaci)
        print(f"   ➤ [ALGO][{typ}] 🎯 ZMYSŁ TRADERA ({tryb}): {wybor['symbol']} ({wybor['warunek']})")
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
    if not kandydaci: return None

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

    priorytety_czasu = { "godzinowa": 1, "4-godzinna": 2, "jednodniowa": 3, "dzienna": 3, "tygodniowa": 4 }
    
    # Sortujemy: Najpierw AI, potem wynik z Pamięci (Duchy), na końcu czas
    wolni_kandydaci.sort(key=lambda x: (
        0 if x.get("zrodlo") == "AI" else 1,    
        -x.get("szansa_ducha", 50.0),                   
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
        print(f"☀️ TRYB DZIENNY. AI i Zmysł Tradera współpracują.")

    fng = market.get("sentiment", {})
    sentyment_val = fng.get('value', 50)
    sentyment_klasa = fng.get('value_classification', 'Neutral')
    print(f"🎭 Rynek: Sentyment {sentyment_val} ({sentyment_klasa})")
    
    wstepne_strategie = []
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

                            krolowie = ["BTC", "ETH", "SOL", "XRP", "XRPUSDT", "SOLUSDT", "BTCUSDT", "ETHUSDT"] 
                            if sym not in krolowie and typ in ["jednodniowa", "tygodniowa"]:
                                continue

                            ikona = "✅" if decyzja == "TAK" else "❌"
                            print(f"   {ikona} {decyzja} [{typ}]: {sym} -> {warunek}")

                            if decyzja == "TAK":
                                s = {
                                    "nazwa": f"{sym}_AI_{typ}", "symbol": sym, "typ": typ,
                                    "warunek": warunek, "oczekiwany_ruch": "wzrost", 
                                    "zrodlo": "AI"  
                                }
                                wstepne_strategie.append(s)
                                zablokowane_pary_tak.append((sym, typ))
                                zablokowane_pary_tak.append((sym_short, typ))
                else:
                    print(f"   ⚠️ Błąd parsowania odpowiedzi AI: {msg}")

        except Exception as e:
            print(f"   ⚠️ Błąd AI (Critical): {e}")

    # --- SEKCJA ZMYSŁU TRADERA ---
    print("-" * 50)
    print(f"🛡️ [2] ZMYSŁ TRADERA (Kontekstowa Analiza Rynku):")
    
    typy_wszystkie = ["godzinowa", "4-godzinna", "jednodniowa", "tygodniowa"]

    for typ in typy_wszystkie:
        awaryjne = analiza_techniczna_zapasowa(typ, market, zablokowane_pary_tak)
        if awaryjne:
            awaryjne[0]['zrodlo'] = f"Instynkt ({sentyment_klasa})"
            wstepne_strategie.extend(awaryjne)

    # --- WERYFIKACJA W BAZIE DUCHÓW ---
    finalne_strategie = []
    print("-" * 50)
    print(f"👻 [3] WERYFIKACJA HISTORYCZNA (Baza Duchów):")
    
    for kandydat in wstepne_strategie:
        status, szansa = weryfikuj_przez_duchy(kandydat, market, db)
        kandydat['szansa_ducha'] = szansa
        
        if status == "ZNANE":
            if szansa >= 60:
                print(f"   🟢 [DOBRE WSPOMNIENIE] Skuteczność {szansa:.0f}% -> Potwierdzam {kandydat['symbol']}")
                finalne_strategie.append(kandydat)
            elif szansa <= 30:
                print(f"   🚫 [ZŁE WSPOMNIENIE] Znana pułapka! (Tylko {szansa:.0f}% sukcesu) -> Odrzucam {kandydat['symbol']}")
            else:
                print(f"   ⚖️  [MIESZANE WSPOMNIENIA] Skuteczność {szansa:.0f}%. Gram na instynkt -> {kandydat['symbol']}")
                finalne_strategie.append(kandydat)
        else:
            print(f"   🕵️  [NOWY GRUNT] Brak danych w bazie dla tego układu. Ufam intuicji ({kandydat['zrodlo']}) -> {kandydat['symbol']}")
            finalne_strategie.append(kandydat)

    # --- FINALE ---
    print("=" * 50)
    if finalne_strategie:
        print(f"🚀 SUKCES! Znaleziono i zweryfikowano {len(finalne_strategie)} pewnych opcji.")
        save_strategies(finalne_strategie)
        
        wybrana = wybierz_najlepsza_strategie(finalne_strategie)
        
        if wybrana:
            decyzja_dla_schedulera = {
                "akcja": "KUP", 
                "symbol": wybrana["symbol"],
                "typ_strategii": wybrana["typ"], 
                "zrodlo": wybrana.get("zrodlo", "Nieznane"),
                "uzasadnienie": wybrana["warunek"],
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            save_brain(decyzja_dla_schedulera)
            print(f"🧠 [CONNECT] Wybrano do realizacji: {wybrana['symbol']} [{wybrana['typ']}] (Źródło: {wybrana.get('zrodlo')})")
        else:
            print("🧠 [CONNECT] Brak nowych unikalnych strategii (wszystkie sloty zajęte).")
            save_brain({"akcja": "CZEKAJ", "powod": "Dublowanie strategii"})

    else:
        print("💤 PUSTO. Baza odrzuciła sygnały lub brak okazji.")
        save_brain({"akcja": "CZEKAJ", "powod": "Brak strategii / Pułapka"})
        try:
            with open(STRATEGIE_TEMP_PATH, "w", encoding="utf-8") as f: json.dump([], f)
        except: pass

if __name__ == "__main__":
    main()