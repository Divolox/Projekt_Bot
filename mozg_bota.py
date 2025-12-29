import json
from datetime import datetime, timezone
import time
import random
import statistics
from ai_helper import ask_ai
from strategia_helper import save_strategies, extract_knowledge
from data_storage import wczytaj_strategie_bota 
from utils_data import analizuj_pelny_obraz, calc_rsi

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
    strategie = wczytaj_strategie_bota()
    ocenione = [s for s in strategie if s.get("status") == "oceniona"]
    ocenione.sort(key=lambda x: x.get("czas_utworzenia", ""), reverse=True)
    if not ocenione: return "Brak historii."
    raport = ""
    for s in ocenione[:5]:
        sym = s.get("symbol")
        typ = s.get("typ")
        wynik = s.get("ocena", {}).get("wynik", "?")
        raport += f"- {sym} [{typ}]: {wynik}\n"
    return raport

# =========================================================
# 🧠 INTELIGENTNY ALGORYTM (Adaptacyjny)
# =========================================================
def analiza_techniczna_zapasowa(typ, market_data):
    kandydaci = []
    mapa_int = {"godzinowa": "1h", "4-godzinna": "4h", "jednodniowa": "1d", "tygodniowa": "1w"}
    interwal = mapa_int.get(typ, "1h")

    # --- 1. SPRAWDZAMY SENTYMENT RYNKU ---
    try:
        fng = int(market_data.get("sentiment", {}).get("value", 50))
    except: fng = 50

    # --- 2. AUTOMATYCZNE DOSTRAJANIE (AUTOPILOT) ---
    
    # Domyślne wartości (Neutralne)
    limit_rsi_dip = 45
    min_vol_ratio = 1.0
    tryb = "NEUTRALNY"

    if fng <= 35: 
        # FEAR (Strach - To co mamy teraz): ZACISKAMY PAS
        tryb = "DEFENSYWNY (Strach)"
        limit_rsi_dip = 32   # Tylko okazje życia (poprzednio 55 - to był błąd)
        min_vol_ratio = 1.2  # Tylko duży wolumen
    
    elif fng >= 60:
        # GREED (Chciwość - Jak rynek ruszy): LUZUJEMY
        tryb = "AGRESYWNY (Hossa)"
        limit_rsi_dip = 60   # Kupujemy trendy
        min_vol_ratio = 0.8  # Akceptujemy mniejszy wolumen (bo wszystko rośnie)
        
    # Korekta dla strategii godzinowej (zawsze ostrożniej)
    if "godz" in typ:
        limit_rsi_dip -= 4
        min_vol_ratio += 0.3

    powod_odrzucenia_btc = "Brak danych"

    for symbol, intervals in market_data.get("data", {}).items():
        swiece = intervals.get(interwal, [])
        if not swiece or len(swiece) < 20: continue
        
        ceny = [x['c'] for x in swiece]
        volumeny = [x['v'] for x in swiece]
        cena_akt = ceny[-1]
        rsi = calc_rsi(swiece)
        sma_20 = statistics.mean(ceny[-20:]) 
        trend = "wzrost" if cena_akt > sma_20 else "spadek"
        
        avg_vol = statistics.mean(volumeny[-5:])
        vol_ratio = volumeny[-1] / avg_vol if avg_vol > 0 else 0
        
        odrzut = ""
        
        # LOGIKA FILTRACJI (Zależna od trybu)
        if vol_ratio < min_vol_ratio:
            # W strachu wymagamy potwierdzenia wolumenem. W hossie mniej.
            if not (rsi < 25): # Jak jest totalny krach, to bierzemy nawet bez wolumenu
                odrzut = f"Słaby wolumen ({vol_ratio:.1f}x vs {min_vol_ratio}x)"

        elif trend == "spadek" and rsi > limit_rsi_dip:
             # To chroni przed łapaniem noży w połowie (SOL -5%)
             odrzut = f"Spadek + RSI {rsi:.1f} za wysokie (Limit: {limit_rsi_dip})"

        elif trend == "wzrost" and rsi >= 70:
             # Nawet w hossie nie kupujemy szczytów
             odrzut = f"Wykupione ({rsi:.1f})"

        # Info o BTC dla usera
        if symbol == "BTC": powod_odrzucenia_btc = odrzut if odrzut else "Nieznany"
        
        if odrzut: continue

        # --- SUKCES - DODAJEMY ---
        # SCENARIUSZ A: DIP (Kupno dołka)
        if rsi <= limit_rsi_dip:
            kandydaci.append({
                "nazwa": f"{symbol}_SmartDip", "symbol": symbol, "typ": typ,
                "warunek": f"DIP ({tryb}) RSI {rsi:.1f} + Vol {vol_ratio:.1f}x",
                "oczekiwany_ruch": "wzrost", "pewnosc": "średnia"
            })
        
        # SCENARIUSZ B: TREND (Tylko w Hossie/Neutral)
        elif trend == "wzrost" and fng > 40 and rsi < 65:
            kandydaci.append({
                "nazwa": f"{symbol}_TrendRide", "symbol": symbol, "typ": typ,
                "warunek": f"TREND ({tryb}) RSI {rsi:.1f} + Vol {vol_ratio:.1f}x",
                "oczekiwany_ruch": "wzrost", "pewnosc": "wysoka"
            })

    if kandydaci:
        # W strachu BTC/ETH bezpieczniejsze
        if fng < 40:
            kandydaci.sort(key=lambda x: 3 if x['symbol'] == 'BTC' else (2 if x['symbol'] == 'ETH' else 1), reverse=True)
        
        wybor = random.choice(kandydaci)
        print(f"   ➤ [ALGO] 🎯 CEL ({tryb}): {wybor['symbol']} ({wybor['warunek']})")
        return [wybor]
    
    # Logujemy powód odrzucenia BTC
    if "tyg" not in typ:
        print(f"   ➤ [ALGO] 💤 Pas ({tryb}). BTC: {powod_odrzucenia_btc}")
    return []

def generuj_raport_4_slotowy(obraz, historia, sentyment):
    prompt = f"""
    Jesteś ZAWODOWYM TRADEREM.
    Sytuacja rynkowa: {sentyment}.
    
    ZADANIE: Decyzja TAK/NIE dla 4 interwałów (1H, 4H, 1D, 1W).
    
    ZASADY ADAPTACYJNE:
    1. JEŚLI STRACH (Fear): Bądź bardzo ostrożny. Szukaj tylko głębokich dołków (RSI < 30) i dużego wolumenu.
    2. JEŚLI CHCIWOŚĆ (Greed): Szukaj trendów wzrostowych i wybicia.
    3. JEŚLI "NIE": Napisz krótko dlaczego (max 5 słów).
    
    DANE:
    {obraz}
    
    FORMAT JSON:
    [
      {{ "typ": "godzinowa", "decyzja": "TAK/NIE", "symbol": "...", "warunek": "...", "oczekiwany_ruch": "wzrost" }},
      ...
    ]
    """
    return ask_ai(prompt)

def main():
    market = load_data(RYNEK_PATH)
    if not market.get("data"): return

    print("\n" + "="*50)
    print(f"🧠 MÓZG BOTA: START ANALIZY ({datetime.now().strftime('%H:%M')})")
    print("="*50)

    # --- SIESTA (Oszczędzanie limitu) ---
    godzina = datetime.now().hour
    tryb_tylko_algo = False
    
    if 18 <= godzina < 23:
        tryb_tylko_algo = True
        print(f"🌙 TRYB NOCNY (SIESTA 18-23). AI odpoczywa.")
    else:
        print(f"☀️ TRYB DZIENNY. AI i Algorytm współpracują.")

    fng = market.get("sentiment", {})
    sentyment_str = f"Sentyment: {fng.get('value')} ({fng.get('value_classification')})"
    print(f"🎭 Rynek: {sentyment_str}")
    
    finalne_strategie = []
    znalezione_typy = [] 

    # --- KROK 1: AI ---
    if not tryb_tylko_algo:
        print("-" * 50)
        print(f"🤖 [1] KONSULTACJA AI (Gemini):")
        
        obraz_rynku = ""
        for sym, intervals in market["data"].items():
            obraz_rynku += f"\nANALIZA {sym}:\n"
            obraz_rynku += analizuj_pelny_obraz(intervals)

        try:
            resp = generuj_raport_4_slotowy(obraz_rynku, przygotuj_historie(), sentyment_str)
            if resp:
                raport, msg = extract_knowledge(resp)
                if raport:
                    for pozycja in raport:
                        typ = pozycja.get("typ", "nieznany")
                        decyzja = pozycja.get("decyzja", "NIE")
                        sym = pozycja.get("symbol", "-")
                        warunek = pozycja.get("warunek", "Brak powodu")
                        
                        if decyzja == "TAK" and sym != "-":
                            s = {
                                "nazwa": f"{sym}_AI_{typ}", "symbol": sym, "typ": typ,
                                "warunek": warunek, "oczekiwany_ruch": "wzrost", 
                                "pewnosc": "wysoka", "zrodlo": "AI"
                            }
                            finalne_strategie.append(s)
                            znalezione_typy.append(typ)
                            print(f"   ✅ TAK [{typ}]: {sym} -> {warunek}")
                        else:
                            print(f"   ❌ NIE [{typ}]: {warunek}")
        except Exception as e:
            print(f"   ⚠️ Błąd AI: {e}")

    # --- KROK 2: ALGORYTM (ADAPTACYJNY) ---
    print("-" * 50)
    print(f"🛡️ [2] WERYFIKACJA MATEMATYCZNA (Snajper):")
    
    typy_do_sprawdzenia = ["godzinowa", "4-godzinna", "jednodniowa", "tygodniowa"]
    if not tryb_tylko_algo:
        typy_do_sprawdzenia = [t for t in typy_do_sprawdzenia if t not in znalezione_typy]

    for typ in typy_do_sprawdzenia:
        awaryjne = analiza_techniczna_zapasowa(typ, market)
        if awaryjne:
            awaryjne[0]['zrodlo'] = f"Algorytm ({market.get('sentiment', {}).get('value_classification', 'Auto')})"
            finalne_strategie.extend(awaryjne)

    print("=" * 50)
    if finalne_strategie:
        print(f"🚀 SUKCES! Znaleziono {len(finalne_strategie)} strategii.")
        save_strategies(finalne_strategie)
    else:
        print("💤 PUSTO. Cierpliwość to klucz.")
        try:
            with open(STRATEGIE_TEMP_PATH, "w", encoding="utf-8") as f: json.dump([], f)
        except: pass

if __name__ == "__main__":
    main()