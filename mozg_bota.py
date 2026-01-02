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
    ocenione = [s for s in strategie if isinstance(s, dict) and s.get("status") == "oceniona"]
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
def analiza_techniczna_zapasowa(typ, market_data, zablokowane_pary=[]):
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
        
        # Sprawdzamy, czy AI już podjęło decyzję (TAK) dla tej pary
        if (symbol, typ) in zablokowane_pary or (symbol_usdt, typ) in zablokowane_pary:
            continue

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
        
        if vol_ratio < min_vol_ratio:
            if not (rsi < 25): odrzut = f"Słaby wolumen ({vol_ratio:.1f}x vs {min_vol_ratio}x)"
        elif trend == "spadek" and rsi > limit_rsi_dip:
             odrzut = f"Spadek + RSI {rsi:.1f} za wysokie"
        elif trend == "wzrost" and rsi >= 70:
             odrzut = f"Wykupione ({rsi:.1f})"

        if odrzut:
            print(f"   ➤ [ALGO][{typ}] 💤 Pas {symbol}: {odrzut}")
            continue

        if rsi <= limit_rsi_dip:
            kandydaci.append({
                "nazwa": f"{symbol}_SmartDip", "symbol": symbol, "typ": typ,
                "warunek": f"DIP ({tryb}) RSI {rsi:.1f} + Vol {vol_ratio:.1f}x",
                "oczekiwany_ruch": "wzrost", "pewnosc": "średnia"
            })
        elif trend == "wzrost" and fng > 40 and rsi < 65:
            kandydaci.append({
                "nazwa": f"{symbol}_TrendRide", "symbol": symbol, "typ": typ,
                "warunek": f"TREND ({tryb}) RSI {rsi:.1f} + Vol {vol_ratio:.1f}x",
                "oczekiwany_ruch": "wzrost", "pewnosc": "wysoka"
            })

    if kandydaci:
        if fng < 40:
            kandydaci.sort(key=lambda x: 3 if x['symbol'] == 'BTC' else (2 if x['symbol'] == 'ETH' else 1), reverse=True)
        wybor = random.choice(kandydaci)
        print(f"   ➤ [ALGO][{typ}] 🎯 CEL ({tryb}): {wybor['symbol']} ({wybor['warunek']})")
        return [wybor]
    
    return []

def generuj_raport_4_slotowy(obraz, historia, sentyment_str, sentyment_wartosc, dostepne_coiny):
    # FIX: Dodałem argumenty sentyment_str i sentyment_wartosc, żeby prompt ich widział
    lista_coinow_str = ", ".join(dostepne_coiny)

    prompt = f"""
    Jesteś Senior Traderem AI z 20-letnim doświadczeniem w krypto.
    Twoim celem jest ZYSKOWNY HANDEL SWINGOWY, a nie hazard.
    
    === SYTUACJA RYNKOWA ===
    Globalny Sentyment: {sentyment_str} (Index: {sentyment_wartosc}/100)
    
    === TWOJA STRATEGIA (INTELIGENCJA) ===
    1. FILTR BITCOINA (Najważniejsze):
       - Jeśli BTC spada dynamicznie -> ODRZUCAJ WSZYSTKIE ALTCOINY (Risk Off).
       - Jeśli BTC jest stabilny lub rośnie -> Szukaj okazji (Risk On).
       
    2. ANALIZA TECHNICZNA (Szukaj Konfluencji):
       - RSI < 30 + Extreme Fear: To zazwyczaj okazja na "Odbicie Zdechłego Kota" lub odwrócenie. BIERZ, jeśli wolumen nie jest paniczny.
       - RSI > 70 + Greed: Ryzyko korekty. Nie kupuj, chyba że to wybicie (Breakout) na ogromnym wolumenie.
       - Volume Ratio: Jeśli < 0.5 -> Rynek martwy, unikaj. Jeśli > 2.0 -> Coś się dzieje (uwaga na pompy).
       
    3. KONSEKWENCJA:
       - Nie "zgaduj". Jeśli nie ma czystego sygnału -> Decyzja: NIE.
       - Lepiej stracić okazję niż stracić kapitał.

    DANE DO ANALIZY (PRZEANALIZUJ KAŻDĄ PARĘ INDYWIDUALNIE):
    {obraz}
    
    TWOJA DECYZJA (JSON):
    {{
        "SYMBOL": {{ 
            "decyzja": "TAK" lub "NIE", 
            "powod": "Opisz dlaczego, odnosząc się do BTC i struktury rynku (max 1 zdanie)" 
        }},
        ...
    }}
    """
    return ask_ai(prompt)

def wybierz_najlepsza_strategie(kandydaci, aktywne_pozycje):
    if not kandydaci: return None

    # 1. Zbieramy zajęte sloty
    zajete_sloty = set()
    for id_pozycji, p in aktywne_pozycje.items():
        if "_" in id_pozycji:
            zajete_sloty.add(id_pozycji)
        else:
            sym = p.get("symbol", "")
            typ = p.get("typ", "STANDARD")
            zajete_sloty.add(f"{sym}_{typ}")

    # 2. Filtrujemy kandydatów
    wolni_kandydaci = []
    for k in kandydaci:
        symbol = k["symbol"]
        typ = k["typ"]
        unikalne_id = f"{symbol}_{typ}"
        
        if unikalne_id in zajete_sloty:
            print(f"   ⚠️ Pomijam {symbol} [{typ}] - ten slot jest zajęty.")
            continue
        wolni_kandydaci.append(k)

    if not wolni_kandydaci:
        return None

    # 3. Sortowanie
    priorytety = { "godzinowa": 1, "4-godzinna": 2, "jednodniowa": 3, "dzienna": 3, "tygodniowa": 4 }
    
    wolni_kandydaci.sort(key=lambda x: (
        0 if x.get("pewnosc") == "wysoka" else 1, 
        priorytety.get(x["typ"], 99)
    ))

    return wolni_kandydaci[0]

def main():
    market = load_data(RYNEK_PATH)
    if not market.get("data"): return

    print("\n" + "="*50)
    print(f"🧠 MÓZG BOTA: START ANALIZY ({datetime.now().strftime('%H:%M')})")
    print("="*50)

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
    sentyment_str = f"Sentyment: {sentyment_val} ({sentyment_klasa})"
    print(f"🎭 Rynek: {sentyment_str}")
    
    finalne_strategie = []
    zablokowane_pary_tak = [] 

    if not tryb_tylko_algo:
        print("-" * 50)
        print(f"🤖 [1] KONSULTACJA AI (Gemini):")
        
        obraz_rynku = ""
        dostepne_coiny = list(market["data"].keys())
        
        for sym, intervals in market["data"].items():
            obraz_rynku += f"\nANALIZA {sym}:\n"
            obraz_rynku += analizuj_pelny_obraz(intervals)

        try:
            # FIX: Przekazujemy rozbite wartości sentymentu
            resp = generuj_raport_4_slotowy(obraz_rynku, przygotuj_historie(), sentyment_klasa, sentyment_val, dostepne_coiny)
            
            if resp:
                raport, msg = extract_knowledge(resp)
                if raport:
                    for pozycja in raport:
                        if not isinstance(pozycja, dict): continue

                        typ = pozycja.get("typ", "nieznany")
                        decyzja = pozycja.get("decyzja", "NIE")
                        sym = pozycja.get("symbol", "NIEZNANY")
                        warunek = pozycja.get("warunek", "Brak powodu")

                        sym_short = sym.replace("USDT", "")

                        if decyzja == "TAK":
                            s = {
                                "nazwa": f"{sym}_AI_{typ}", "symbol": sym, "typ": typ,
                                "warunek": warunek, "oczekiwany_ruch": "wzrost", 
                                "pewnosc": "wysoka", "zrodlo": "AI"
                            }
                            finalne_strategie.append(s)
                            print(f"   ✅ TAK [{typ}]: {sym} -> {warunek}")
                            
                            zablokowane_pary_tak.append((sym, typ))
                            zablokowane_pary_tak.append((sym_short, typ))
                        else:
                            # Opcjonalnie można odkomentować
                            # print(f"   ❌ NIE [{typ}]: {sym} -> {warunek}")
                            pass
                else:
                    print(f"   ⚠️ Błąd parsowania odpowiedzi AI: {msg}")

        except Exception as e:
            print(f"   ⚠️ Błąd AI (Critical): {e}")

    print("-" * 50)
    print(f"🛡️ [2] WERYFIKACJA MATEMATYCZNA (Snajper):")
    
    typy_wszystkie = ["godzinowa", "4-godzinna", "jednodniowa", "tygodniowa"]

    for typ in typy_wszystkie:
        awaryjne = analiza_techniczna_zapasowa(typ, market, zablokowane_pary_tak)
        if awaryjne:
            awaryjne[0]['zrodlo'] = f"Algorytm ({sentyment_klasa})"
            finalne_strategie.extend(awaryjne)

    print("=" * 50)
    if finalne_strategie:
        print(f"🚀 SUKCES! Znaleziono {len(finalne_strategie)} kandydatów.")
        save_strategies(finalne_strategie)
        
        aktywne = wczytaj_strategie_bota()
        wybrana = wybierz_najlepsza_strategie(finalne_strategie, aktywne)
        
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