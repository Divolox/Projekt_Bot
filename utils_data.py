import statistics

# ==========================================
# 🛠️ TWOJE ORYGINALNE FUNKCJE (ZACHOWANE)
# ==========================================

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

def extract_ohlc(market_data, symbol):
    """Wyciąga świece 1D dla symbolu z formatu rynek.json"""
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
        # Fix: Używamy 'open' jeśli jest (nowy format), lub szacujemy
        open_price = c.get('open', c['c']) 
        close_price = c['c']
        
        zmiana = ((close_price - open_price) / open_price) * 100
            
        ikona = "🟢" if zmiana > 0 else "🔴"
        opis += f"Dzień {i+1}: {ikona} {zmiana:.2f}% (Vol: {int(c['v'])})\n"
        
    return opis

# ==========================================
# 🧠 NOWOŚĆ: DYNAMIKA I WZROK (DODANO)
# ==========================================

def analizuj_dynamike_swiecy(swieca):
    """
    Analizuje kształt pojedynczej świecy matematycznie.
    """
    # Obsługa obu formatów kluczy (c/v i close/vol)
    cl = swieca.get('close', swieca.get('c'))
    hi = swieca.get('high', swieca.get('h'))
    lo = swieca.get('low', swieca.get('l'))
    # Szukamy open, jeśli brak to symulujemy (dla bezpieczeństwa)
    op = swieca.get('open', swieca.get('o', cl)) 

    if cl is None: return "Błąd danych"
    
    body = abs(cl - op)
    upper_shadow = hi - max(op, cl)
    lower_shadow = min(op, cl) - lo
    total_range = hi - lo
    
    if total_range == 0: return "Doji (Brak ruchu)"
    
    body_proc = body / total_range
    direction = "Wzrostowa" if cl > op else "Spadkowa"
    
    opis = []
    
    # 1. Siła korpusu
    if body_proc > 0.8: opis.append(f"Silna świeca {direction} (Pełne body)")
    elif body_proc < 0.1: opis.append("Doji (Niepewność)")
    else: opis.append(f"Świeca {direction}")
    
    # 2. Cienie (Psychologia rynku)
    if lower_shadow > (body * 2) and lower_shadow > upper_shadow:
        opis.append("Długi dolny cień -> PRESJA KUPUJĄCYCH (Odrzucenie dna)")
    elif upper_shadow > (body * 2) and upper_shadow > lower_shadow:
        opis.append("Długi górny cień -> PRESJA SPRZEDAJĄCYCH (Odrzucenie szczytu)")
        
    return ", ".join(opis)

def buduj_obraz_rynku_v2(symbol, symbol_data, db_handler):
    """
    Łączy dane z JSON (krótkie) z danymi z SQL (długie/dno).
    """
    raport = f"\nANALIZA {symbol}:\n"
    
    # 1. Sprawdzanie Dna Historycznego (SQL Support)
    # Patrzymy 30 dni wstecz na interwale 1d
    dno_30d = db_handler.znajdz_dno_historyczne(symbol, "1d", 30)
    
    current_price = 0
    if "1h" in symbol_data and symbol_data["1h"]:
        # Obsługa klucza 'c' (stary) lub 'close' (nowy)
        last_candle = symbol_data["1h"][-1]
        current_price = last_candle.get("c", last_candle.get("close", 0))
        
    if dno_30d and current_price > 0:
        odleglosc = ((current_price - dno_30d) / dno_30d) * 100
        raport += f"   🛡️ POZYCJA WZG. DNA (30 dni): Cena {current_price} vs Dno {dno_30d} (+{odleglosc:.2f}%)\n"
        if odleglosc < 5.0:
            raport += "      🚨 UWAGA: Bardzo blisko wsparcia! Okazja na odbicie.\n"
        elif odleglosc > 50.0:
            raport += "      ⚠️ UWAGA: Wysoko od dna. Ryzyko korekty.\n"
            
    # 2. Dynamika Ostatniej Świecy (1H i 4H)
    for interwal in ["1h", "4h"]:
        candles = symbol_data.get(interwal, [])
        if candles:
            ostatnia = candles[-1]
            dynamika = analizuj_dynamike_swiecy(ostatnia)
            rsi = calc_rsi(candles)
            trend = get_trend(candles)
            
            raport += f"   - [{interwal}] Trend: {trend}, RSI: {rsi}, Kształt: {dynamika}\n"
            
    return raport