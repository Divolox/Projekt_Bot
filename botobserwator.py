import json
import requests
import time
import sys
import os
from datetime import datetime, timezone

# --- DODANO: Obsługa Bazy Danych ---
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from database_handler import DatabaseHandler
except ImportError:
    print("❌ Błąd: Brak pliku database_handler.py")
    sys.exit()
# -----------------------------------

def get_fear_and_greed():
    """Pobiera wskaźnik sentymentu"""
    try:
        url = "https://api.alternative.me/fng/"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0]
    except Exception as e:
        print(f"⚠️ Błąd Fear&Greed: {e}")
    return {"value": "50", "value_classification": "Neutral"}

def get_binance_ohlc(symbol, interval, limit):
    """
    Pobiera świece z Binance. 
    """
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol.replace("-", "").upper(), "interval": interval, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            ohlc = []
            for e in data:
                ohlc.append({
                    "c": float(e[4]), # Close price
                    "h": float(e[2]), 
                    "l": float(e[3]), 
                    "v": float(e[5]), 
                    "time": int(e[0] / 1000), 
                    "open": float(e[1]),
                    "high": float(e[2]),
                    "low": float(e[3]),
                    "close": float(e[4]),
                    "vol": float(e[5])
                })
            return ohlc
    except Exception as e:
        print(f"⚠️ Błąd Binance {symbol} {interval}: {e}")
    return []

def main():
    print("📡 OBSERWATOR: Pobieram dane (MTF + SQL History)...")
    
    db = DatabaseHandler()
    
    fng = get_fear_and_greed()
    print(f"   🎭 Sentyment Rynku: {fng.get('value')} ({fng.get('value_classification')})")
    
    # --- NOWA LISTA COINÓW (DYWERSYFIKACJA) ---
    symbols = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT",  # Królowie
        "BNBUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT" # Alty
    ]
    
    market_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sentiment": fng,
        "prices": [],
        "data": {} 
    }

    for sym in symbols:
        short_sym = sym.replace("USDT", "")
        market_data["data"][short_sym] = {}
        
        # Konfiguracja interwałów
        intervals_config = {
            "1h": 24,   
            "4h": 20,
            "1d": 60,   
            "1w": 20    
        }
        
        for interv, limit in intervals_config.items():
            ohlc = get_binance_ohlc(sym, interv, limit)
            
            if ohlc:
                # A. JSON
                market_data["data"][short_sym][interv] = ohlc
                # B. SQL
                db.zapisz_swiece(short_sym, interv, ohlc)
            
            time.sleep(0.1) 

        if "1h" in market_data["data"][short_sym] and market_data["data"][short_sym]["1h"]:
            last_price = market_data["data"][short_sym]["1h"][-1]["c"]
            market_data["prices"].append({"symbol": sym, "current_price": last_price})
            print(f"   > {short_sym}: {last_price} USD (SQL Updated)")

    with open("rynek.json", "w", encoding="utf-8") as f:
        json.dump(market_data, f, indent=2)
    
    db.zamknij()
    print("💾 Dane zapisane (JSON + SQL). Baza rośnie.")

if __name__ == "__main__":
    main()