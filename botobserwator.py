import json
import requests
import time
from datetime import datetime, timezone

def get_fear_and_greed():
    """Pobiera wskaźnik sentymentu"""
    try:
        url = "https://api.alternative.me/fng/"
        resp = requests.get(url, timeout=10) # Zwiększyłem timeout dla stabilności
        data = resp.json()
        if "data" in data and len(data["data"]) > 0:
            return data["data"][0]
    except Exception as e:
        print(f"⚠️ Błąd Fear&Greed: {e}")
    return {"value": "50", "value_classification": "Neutral"}

def get_binance_ohlc(symbol, interval, limit):
    """Pobiera świece z Binance. KRYTYCZNE: Musi zawierać 'v' (wolumen)"""
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
                    "h": float(e[2]), # High price
                    "l": float(e[3]), # Low price
                    "v": float(e[5])  # <--- TU JEST WOLUMEN. BEZ TEGO WYWALA BŁĄD.
                })
            return ohlc
    except Exception as e:
        print(f"⚠️ Błąd Binance {symbol} {interval}: {e}")
    return []

def main():
    print("📡 OBSERWATOR: Pobieram dane (1H, 4H, 1D, 1W) + Wolumen...")
    
    # 1. Sentyment
    fng = get_fear_and_greed()
    print(f"   🎭 Sentyment Rynku: {fng.get('value')} ({fng.get('value_classification')})")
    
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]
    
    market_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sentiment": fng,
        "prices": [],
        "data": {} # Tu lądują dane dla utils_data.py
    }

    # 2. Pętla po coinach
    for sym in symbols:
        short_sym = sym.replace("USDT", "")
        market_data["data"][short_sym] = {}
        
        # Pętla po interwałach (MTF)
        intervals = ["1h", "4h", "1d", "1w"]
        
        for interv in intervals:
            ohlc = get_binance_ohlc(sym, interv, 20)
            market_data["data"][short_sym][interv] = ohlc
            time.sleep(0.1) # Lekkie opóźnienie dla API

        # Log dla użytkownika (żebyś widział, że działa)
        if "1h" in market_data["data"][short_sym] and market_data["data"][short_sym]["1h"]:
            last_price = market_data["data"][short_sym]["1h"][-1]["c"]
            market_data["prices"].append({"symbol": sym, "current_price": last_price})
            print(f"   > {short_sym}: {last_price} USD (Pobrano MTF + VSA)")

    # 3. Zapis
    with open("rynek.json", "w", encoding="utf-8") as f:
        json.dump(market_data, f, indent=2)
    print("💾 Dane zapisane poprawnie (Z Wolumenem).")

if __name__ == "__main__":
    main()