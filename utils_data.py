import statistics

# ==========================================
# 🛠️ TWOJE ORYGINALNE FUNKCJE (ZACHOWANE)
# ==========================================

def calc_rsi(data, period=14):
    if not data or len(data) < period + 1: return 50
    closes = [float(x.get('c', x.get('close', 0))) for x in data]
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
    closes = [float(x.get('c', x.get('close', 0))) for x in data]
    sma = statistics.mean(closes[-10:])
    return "Wzrost ↗️" if closes[-1] > sma else "Spadek ↘️"

def analizuj_wolumen(data):
    if not data or len(data) < 5: return "Brak danych"
    volumes = [float(x.get('v', x.get('vol', 0))) for x in data]
    avg_vol = statistics.mean(volumes[-10:]) if len(volumes) >= 10 else statistics.mean(volumes)
    ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1
    
    if ratio > 1.5: return f"WYSOKI ({ratio:.1f}x) 🔥"
    elif ratio < 0.6: return f"NISKI ({ratio:.1f}x) ⚠️"
    return "Normalny"

def get_raw_indicators(data):
    if not data or len(data) < 14: return 50, 1.0
    rsi = calc_rsi(data)
    volumes = [float(x.get('v', x.get('vol', 0))) for x in data]
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
    short_sym = symbol.replace("USDT", "")
    if "data" in market_data:
        if short_sym in market_data["data"]:
            return market_data["data"][short_sym].get("1d", [])
        if symbol in market_data["data"]:
            return market_data["data"][symbol].get("1d", [])
    return []

def analizuj_swiece(ohlc_data):
    if not ohlc_data or len(ohlc_data) < 5:
        return "Brak wystarczających danych świecowych."
    
    opis = ""
    last_5 = ohlc_data[-5:]
    for i, c in enumerate(last_5):
        open_price = float(c.get('open', c.get('o', c.get('c', 0)))) 
        close_price = float(c.get('c', c.get('close', 0)))
        wolumen = float(c.get('v', c.get('vol', 0)))
        
        if open_price == 0: continue
        zmiana = ((close_price - open_price) / open_price) * 100
            
        ikona = "🟢" if zmiana > 0 else "🔴"
        opis += f"Dzień {i+1}: {ikona} {zmiana:.2f}% (Vol: {int(wolumen)})\n"
        
    return opis

def analizuj_dynamike_swiecy(swieca):
    cl = float(swieca.get('close', swieca.get('c', 0)))
    hi = float(swieca.get('high', swieca.get('h', cl)))
    lo = float(swieca.get('low', swieca.get('l', cl)))
    op = float(swieca.get('open', swieca.get('o', cl)))

    if cl == 0: return "Błąd danych"
    
    body = abs(cl - op)
    upper_shadow = hi - max(op, cl)
    lower_shadow = min(op, cl) - lo
    total_range = hi - lo
    
    if total_range == 0: return "Doji (Brak ruchu)"
    
    body_proc = body / total_range
    direction = "Wzrostowa" if cl > op else "Spadkowa"
    
    opis = []
    
    if body_proc > 0.8: opis.append(f"Silna świeca {direction} (Pełne body)")
    elif body_proc < 0.1: opis.append("Doji (Niepewność)")
    else: opis.append(f"Świeca {direction}")
    
    if lower_shadow > (body * 2) and lower_shadow > upper_shadow:
        opis.append("Długi dolny cień -> PRESJA KUPUJĄCYCH (Odrzucenie dna)")
    elif upper_shadow > (body * 2) and upper_shadow > lower_shadow:
        opis.append("Długi górny cień -> PRESJA SPRZEDAJĄCYCH (Odrzucenie szczytu)")
        
    return ", ".join(opis)


# ==========================================
# 📊 SILNIK PRICE ACTION I KORELACJI Z BTC
# ==========================================

def znajdz_wsparcia_i_opory(swiece, cena_akt, okno_szukania=100):
    if not swiece or len(swiece) < 20: return None, None
        
    dane = swiece[-okno_szukania:]
    highs = [float(s.get('high', s.get('h', s.get('c', 0)))) for s in dane]
    lows = [float(s.get('low', s.get('l', s.get('c', 0)))) for s in dane]
    
    szczyty = []
    dolki = []
    
    for i in range(2, len(dane) - 2):
        if highs[i] == max(highs[i-2 : i+3]): szczyty.append(highs[i])
        if lows[i] == min(lows[i-2 : i+3]): dolki.append(lows[i])
        
    opory_powyzej = [s for s in szczyty if s > cena_akt]
    wsparcia_ponizej = [d for d in dolki if d < cena_akt]
    
    najblizszy_opor = min(opory_powyzej) if opory_powyzej else None
    najblizsze_wsparcie = max(wsparcia_ponizej) if wsparcia_ponizej else None
    
    return najblizsze_wsparcie, najblizszy_opor

def okresl_strukture_rynku(swiece):
    if not swiece or len(swiece) < 20: return "Brak danych"
    
    dane = swiece[-50:] 
    highs = [float(s.get('high', s.get('h', s.get('c', 0)))) for s in dane]
    lows = [float(s.get('low', s.get('l', s.get('c', 0)))) for s in dane]
    
    szczyty = [highs[i] for i in range(2, len(dane)-2) if highs[i] == max(highs[i-2:i+3])]
    dolki = [lows[i] for i in range(2, len(dane)-2) if lows[i] == min(lows[i-2:i+3])]
    
    if len(szczyty) >= 2 and len(dolki) >= 2:
        ostatni_szczyt, przedostatni_szczyt = szczyty[-1], szczyty[-2]
        ostatni_dolek, przedostatni_dolek = dolki[-1], dolki[-2]
        
        if ostatni_szczyt > przedostatni_szczyt and ostatni_dolek > przedostatni_dolek:
            return "Struktura Bycza (Wyższe dołki i szczyty - HH, HL)"
        elif ostatni_szczyt < przedostatni_szczyt and ostatni_dolek < przedostatni_dolek:
            return "Struktura Niedźwiedzia (Niższe dołki i szczyty - LH, LL)"
            
    return "Konsolidacja / Brak wyraźnej struktury"

def badaj_sile_wzgledem_btc(rynek_data, symbol_swiece, interwal="1h"):
    """
    Porównuje zachowanie altcoina z Bitcoinem. Wykrywa Względną Siłę (Relative Strength).
    """
    try:
        # Pobieramy świece BTC
        btc_swiece = rynek_data.get("data", {}).get("BTC", {}).get(interwal, [])
        if not btc_swiece: btc_swiece = rynek_data.get("data", {}).get("BTCUSDT", {}).get(interwal, [])
        
        if not btc_swiece or not symbol_swiece: return "Brak korelacji (brak danych)"
        
        # Ostatnia świeca BTC
        btc_ostatnia = btc_swiece[-1]
        btc_op = float(btc_ostatnia.get('open', btc_ostatnia.get('o', btc_ostatnia.get('c', 1))))
        btc_cl = float(btc_ostatnia.get('close', btc_ostatnia.get('c', 1)))
        btc_zmiana = ((btc_cl - btc_op) / btc_op) * 100
        
        # Ostatnia świeca Coina
        sym_ostatnia = symbol_swiece[-1]
        sym_op = float(sym_ostatnia.get('open', sym_ostatnia.get('o', sym_ostatnia.get('c', 1))))
        sym_cl = float(sym_ostatnia.get('close', sym_ostatnia.get('c', 1)))
        sym_zmiana = ((sym_cl - sym_op) / sym_op) * 100
        
        roznica = sym_zmiana - btc_zmiana
        
        if btc_zmiana < -0.5 and sym_zmiana > 0:
            return f"SILNY WBREW RYNKOWI 🟢 (BTC {btc_zmiana:.1f}%, Coin {sym_zmiana:.1f}%)"
        elif btc_zmiana > 0.5 and sym_zmiana < 0:
            return f"SŁABY (TRUP) 🔴 (BTC {btc_zmiana:.1f}%, Coin {sym_zmiana:.1f}%)"
        elif roznica > 1.0:
            return f"Silniejszy od BTC ↗️ (Bije rynek o {roznica:.1f}%)"
        elif roznica < -1.0:
            return f"Słabszy od BTC ↘️ (Odstaje od rynku o {roznica:.1f}%)"
        else:
            return f"Podąża za BTC 🔗"
            
    except Exception as e:
        return "Błąd analizy korelacji"

def buduj_obraz_rynku_v2(symbol, symbol_data, db_handler, rynek_pelny=None):
    raport = f"\n=== ANALIZA {symbol} (PRICE ACTION & KORELACJA) ===\n"
    
    dno_30d = db_handler.znajdz_dno_historyczne(symbol, "1d", 30)
    current_price = 0
    
    if "1h" in symbol_data and symbol_data["1h"]:
        last_candle = symbol_data["1h"][-1]
        current_price = float(last_candle.get("c", last_candle.get("close", 0)))
        
    if dno_30d and current_price > 0:
        odleglosc = ((current_price - dno_30d) / dno_30d) * 100
        raport += f"🛡️ WSPARCIE MAKRO (SQL): Cena {current_price} vs Dno 30D {dno_30d} (+{odleglosc:.2f}%)\n"
            
    for interwal in ["1h", "4h"]:
        candles = symbol_data.get(interwal, [])
        if candles:
            ostatnia = candles[-1]
            dynamika = analizuj_dynamike_swiecy(ostatnia)
            rsi = calc_rsi(candles)
            trend = get_trend(candles)
            
            wsparcie, opor = znajdz_wsparcia_i_opory(candles, current_price)
            struktura = okresl_strukture_rynku(candles)
            
            raport += f"\n📊 INTERWAŁ [{interwal}]:\n"
            raport += f" - Trend SMA: {trend} | RSI: {rsi} | Świeca: {dynamika}\n"
            raport += f" - Struktura Rynku: {struktura}\n"
            
            # Wstrzyknięcie Korelacji z BTC, jeśli podano pełny rynek
            if rynek_pelny and "BTC" not in symbol:
                korelacja = badaj_sile_wzgledem_btc(rynek_pelny, candles, interwal)
                raport += f" - Relacja do BTC: {korelacja}\n"
            
            if wsparcie and opor:
                odl_wsparcie = ((current_price - wsparcie) / wsparcie) * 100
                odl_opor = ((opor - current_price) / current_price) * 100
                raport += f" - Lokalna Podłoga (Wsparcie): {wsparcie:.4f} (-{odl_wsparcie:.2f}% od ceny)\n"
                raport += f" - Lokalny Sufit (Opór): {opor:.4f} (+{odl_opor:.2f}% od ceny)\n"
            
    return raport