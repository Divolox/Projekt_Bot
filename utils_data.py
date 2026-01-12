import statistics

def calc_rsi(data, period=14):
    if not data or len(data) < period + 1: return 50
    closes = [x['c'] for x in data]
    deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
    gains = [d for d in deltas if d > 0]
    losses = [-d for d in deltas if d < 0]
    
    if not gains: return 0
    if not losses: return 100
    
    avg_gain = sum(gains) / len(gains)
    avg_loss = sum(losses) / len(losses)
    
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)

def get_trend(data):
    if not data or len(data) < 10: return "Nieznany"
    closes = [x['c'] for x in data]
    sma = statistics.mean(closes[-10:])
    return "Wzrost ↗️" if closes[-1] > sma else "Spadek ↘️"

def analizuj_wolumen(data):
    if not data or len(data) < 5: return "Brak danych"
    volumes = [x['v'] for x in data]
    avg_vol = statistics.mean(volumes[-10:]) if len(volumes) >= 10 else statistics.mean(volumes)
    ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1
    
    if ratio > 1.5: return f"WYSOKI ({ratio:.1f}x) 🔥"
    elif ratio < 0.6: return f"NISKI ({ratio:.1f}x) ⚠️"
    return "Normalny"

def get_raw_indicators(data):
    """Zwraca surowe liczby dla Evaluatora (RSI i Ratio Wolumenu)"""
    if not data or len(data) < 14: return 50, 1.0
    rsi = calc_rsi(data)
    
    volumes = [x['v'] for x in data]
    avg_vol = statistics.mean(volumes[-10:]) if len(volumes) >= 10 else statistics.mean(volumes)
    vol_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1.0
    
    return rsi, vol_ratio

def analizuj_pelny_obraz(symbol_data):
    raport = ""
    intervals = ["1h", "4h", "1d", "1w"]
    for interval in intervals:
        candles = symbol_data.get(interval)
        if not candles: continue
        
        rsi = calc_rsi(candles)
        trend = get_trend(candles)
        vol_info = analizuj_wolumen(candles)
        
        stan = ""
        if rsi > 70: stan = "⚠️ WYKUPIENIE"
        if rsi < 30: stan = "✅ WYPRZEDANIE"
        
        raport += f"   - {interval}: Trend {trend}, RSI={rsi} {stan}, Wolumen: {vol_info}\n"
    return raport

# --- [DODANE] BRAKUJĄCE FUNKCJE DLA ANALITYKA ---

def extract_ohlc(market_data, symbol):
    """Wyciąga świece 1D dla symbolu z formatu rynek.json"""
    # Obsługa formatu 'data': {'BTC': {'1d': [...]}}
    short_sym = symbol.replace("USDT", "")
    if "data" in market_data:
        if short_sym in market_data["data"]:
            return market_data["data"][short_sym].get("1d", [])
        if symbol in market_data["data"]:
            return market_data["data"][symbol].get("1d", [])
    return []

def analizuj_swiece(ohlc_data):
    """Generuje prosty opis tekstowy ostatnich 5 świec"""
    if not ohlc_data or len(ohlc_data) < 5:
        return "Brak wystarczających danych świecowych."
    
    opis = ""
    last_5 = ohlc_data[-5:]
    for i, c in enumerate(last_5):
        zmiana = ((c['c'] - c['h']) / c['h']) * 100 # To uproszczenie, lepiej (close-open)/open
        # Zakładając że nie mamy open, szacujemy po close vs prev_close
        if i > 0:
            prev = last_5[i-1]['c']
            zmiana = ((c['c'] - prev) / prev) * 100
        else:
            zmiana = 0.0
            
        ikona = "🟢" if zmiana > 0 else "🔴"
        opis += f"Dzień {i+1}: {ikona} {zmiana:.2f}% (Vol: {int(c['v'])})\n"
        
    return opis