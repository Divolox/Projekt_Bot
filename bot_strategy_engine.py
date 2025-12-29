import json
import datetime
import random
from pathlib import Path
from data_storage import zapisz_strategie_bota

def normalize_type(val):
    """
    NAPRAWIONA KOLEJNOŚĆ:
    Najpierw sprawdzamy 'tyg' (tydzień), bo 'tygodniowa' zawiera 'dn'!
    """
    if not val: return "godzinowa"
    val = str(val).lower()
    
    if "4" in val: return "4-godzinna"
    if "tyg" in val or "1w" in val: return "tygodniowa" # Najpierw to!
    if "dn" in val or "1d" in val: return "jednodniowa" # Potem to!
    if "godz" in val or "1h" in val: return "godzinowa"
    
    return "godzinowa"

def czytaj_mozg():
    try:
        with open("mozg.json", "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def czytaj_strategie_ai():
    try:
        with open("strategie.json", "r", encoding="utf-8") as f: return json.load(f)
    except: return []

def czytaj_rynek():
    try:
        with open("rynek.json", "r", encoding="utf-8") as f: return json.load(f)
    except: return {}

def wymysl_strategie(typ_raw="godzinowa"):
    target_typ = normalize_type(typ_raw)
    
    znane_strategie = czytaj_strategie_ai()
    rynek = czytaj_rynek()

    kandydaci = [s for s in znane_strategie if normalize_type(s.get("typ")) == target_typ]
    
    if not kandydaci:
        return 

    bazowa = random.choice(kandydaci)

    symbol_str = bazowa.get("symbol", "BTC").upper().replace("USDT", "")
    start_price = 0
    
    for p in rynek.get("prices", []):
        if symbol_str in p["symbol"]:
            start_price = p["current_price"]
            break
            
    if not start_price and rynek.get("data"):
        if symbol_str in rynek["data"] and "1h" in rynek["data"][symbol_str]:
             try: start_price = rynek["data"][symbol_str]["1h"][-1]["c"]
             except: pass

    nowa_strategia = {
        "id": f"{target_typ}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{random.randint(100,999)}",
        "typ": target_typ,
        "czas_utworzenia": datetime.datetime.now().isoformat(),
        "status": "oczekuje",
        "bazowa_nazwa": bazowa.get("nazwa"),
        "symbol": symbol_str,
        "warunek": bazowa.get("warunek"),
        "oczekiwany_ruch": bazowa.get("oczekiwany_ruch", "nieznany"),
        "start_price": start_price, 
        "zrodlo": "AI + MarketEngine"
    }

    zapisz_strategie_bota(nowa_strategia)
    print(f"[{target_typ}] ✅ Utworzono strategię dla {symbol_str} (Start: {start_price})")