import requests
import time
import sys
import os
from datetime import datetime, timedelta

# ==============================================================================
# 🚀 SKANER 3.0 (AUTO-ADAPTACJA DO SZUMU + ZWIAD 1M + BLOKADA WIELORYBÓW)
# ==============================================================================

# --- 1. INTEGRACJA Z BAZĄ DANYCH ---
current_dir = os.path.dirname(os.path.abspath(__file__)) 
parent_dir = os.path.dirname(current_dir)              
sys.path.append(parent_dir)
os.chdir(parent_dir)

try:
    import portfel_manager as pm
    from database_handler import DatabaseHandler
except ImportError:
    print("❌ BŁĄD KRYTYCZNY: Brak modułów bazy/portfela w folderze nadrzędnym!")
    sys.exit()

db = DatabaseHandler()

# --- 2. KONFIGURACJA STRATEGII ---
MIN_VOL_24H = 450000 
MIN_CENA = 0.00001 

# --- USTAWIENIA ILOŚCIOWE ---
MAX_POZYCJI_SKANERA = 10   
MAX_KUPNO_NA_SKAN = 8      

# --- BEZPIECZNIK (FILTR PANIKI) ---
FILTR_PANIKI_AKTYWACJA = 10  
FILTR_PANIKI_LIMIT = 5       

INTERVAL_SKANOWANIA_NOWYCH = 300 
INTERVAL_OCHRONY = 10            
COOLDOWN_CZAS = 1800      

CFG_AGRESYWNY = { "PRÓG": 2.0, "RSI": 85, "NAZWA": "🔥 FRONTLINE (Pon-Sob)" }
CFG_BEZPIECZNY = { "PRÓG": 2.8, "RSI": 75, "NAZWA": "🛡️ PATROL (Niedziela)" }

BAN_DNI = 3      
PROG_ACCEL = 0.0 
MIN_VOL_MULTI = 0.5 
MAX_VOL_RATIO = 15.0 # 🔥 Twarda blokada na Pump&Dump (Pułapka na leszczy)

historia_cen_local = {} 

def pobierz_konfiguracje():
    return CFG_BEZPIECZNY if datetime.today().weekday() == 6 else CFG_AGRESYWNY

def get_binance_prices():
    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        resp = requests.get(url, timeout=15).json()
        return {x['symbol']: x for x in resp if x['symbol'].endswith('USDT')}
    except: return {}

# ==============================================================================
# 👁️ DRUGIE OKO: ZWIAD BOJOWY (1-MINUTOWY)
# ==============================================================================
def zwiad_bojowy(symbol):
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=15"
        resp = requests.get(url, timeout=10).json()
        
        if not resp or len(resp) < 5: return 50, 1.0, False, "Brak danych"
        
        closes = [float(x[4]) for x in resp]
        opens = [float(x[1]) for x in resp]
        highs = [float(x[2]) for x in resp]
        volumes = [float(x[5]) for x in resp]

        # 1. RSI
        deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
        gains = [d for d in deltas if d > 0]
        losses = [-d for d in deltas if d < 0]
        
        rsi = 50
        if not gains: rsi = 0
        elif not losses: rsi = 100
        else:
            avg_gain = sum(gains) / len(gains)
            avg_loss = sum(losses) / len(losses)
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        # 2. Skok Wolumenu
        ostatni_vol = volumes[-1]
        sredni_vol = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else 1
        vol_ratio = ostatni_vol / sredni_vol if sredni_vol > 0 else 1.0

        # 3. DETEKCJA POLA MINOWEGO (Pułapka na leszczy)
        ostatnie_close = closes[-1]
        ostatnie_open = opens[-1]
        ostatnie_high = highs[-1]
        
        rozmiar_swiecy = abs(ostatnie_close - ostatnie_open)
        gorny_knot = ostatnie_high - max(ostatnie_close, ostatnie_open)
        
        if gorny_knot > (rozmiar_swiecy * 2.0) and rozmiar_swiecy > 0:
            return rsi, vol_ratio, True, "KNOT ZDRADY (Dystrybucja wieloryba na szczycie)"
            
        if len(volumes) >= 3:
            if volumes[-1] < volumes[-2] < volumes[-3] and closes[-1] > closes[-3]:
                return rsi, vol_ratio, True, "DYWERGENCJA (Rośnie na pustym baku)"

        return rsi, vol_ratio, False, "CZYSTO"

    except Exception as e: 
        return 50, 1.0, False, "Błąd zwiadu"

# ==============================================================================
# 🧠 MICRO-SKANER (BADANIE TRANSAKCJI NA ŻYWO)
# ==============================================================================
def badanie_presji_transakcji(symbol):
    try:
        url = f"https://api.binance.com/api/v3/trades?symbol={symbol}&limit=50"
        resp = requests.get(url, timeout=5).json()
        
        kupno_vol = 0
        sprzedaz_vol = 0
        
        for trade in resp:
            vol = float(trade['qty']) * float(trade['price'])
            if trade['isBuyerMaker']:
                sprzedaz_vol += vol
            else:
                kupno_vol += vol
                
        total_vol = kupno_vol + sprzedaz_vol
        if total_vol == 0: return False, "Brak obrotu"
        
        procent_kupna = (kupno_vol / total_vol) * 100
        
        if procent_kupna < 40.0:
            return True, f"PUŁAPKA (Agresywna sprzedaż: {100-procent_kupna:.0f}%)"
        else:
            return False, f"CZYSTO (Presja kupna: {procent_kupna:.0f}%)"

    except Exception as e:
        return False, "Brak danych z orderbooka"

# --- FIZYKA ---
def oblicz_przyspieszenie(symbol, current_price):
    teraz = time.time()
    if symbol not in historia_cen_local:
        historia_cen_local[symbol] = []
    
    historia_cen_local[symbol].append({"c": current_price, "t": teraz})
    historia_cen_local[symbol] = [x for x in historia_cen_local[symbol] if teraz - x['t'] < 240]
    
    dane = historia_cen_local[symbol]
    if len(dane) < 3: return 0.1 
    
    p_teraz = dane[-1]['c']
    p_1min = next((x['c'] for x in reversed(dane) if teraz - x['t'] >= 60), None)
    p_2min = next((x['c'] for x in reversed(dane) if teraz - x['t'] >= 120), None)
    
    if not p_1min or not p_2min: return 0.1
    
    v1 = ((p_teraz - p_1min) / p_1min) * 100 
    v2 = ((p_1min - p_2min) / p_2min) * 100 
    
    return v1 - v2 

# --- AUTO-ADAPTACJA (CHIRURGIA ZMIENNOŚCI) ---
def zmierz_szum(symbol):
    """Mierzy wibracje monety (high-low z 15 minut), żeby ustawić idealne fotele"""
    try:
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1m&limit=15"
        resp = requests.get(url, timeout=5).json()
        szumy = []
        for k in resp:
            high = float(k[2])
            low = float(k[3])
            if low > 0:
                szumy.append(((high - low) / low) * 100)
        
        if not szumy: return 1.5
        
        sredni_szum = sum(szumy) / len(szumy)
        return max(0.5, min(sredni_szum, 4.0)) # Szum w granicach racjonalności (0.5% do 4.0%)
    except:
        return 1.5 

# --- SQL ---
def pobierz_pozycje_skanera_z_bazy():
    try:
        db.cursor.execute("SELECT unikalne_id, symbol, cena_wejscia, czas_wejscia, max_zysk FROM aktywne_pozycje WHERE zrodlo='SKANER'")
        rows = db.cursor.fetchall()
        pozycje_dict = {}
        for r in rows:
            uid, sym, cena, czas, max_z = r
            pozycje_dict[sym] = {
                'unikalne_id': uid,
                'symbol': sym,
                'cena_wejscia': cena,
                'czas_zakupu': czas, 
                'max_zysk': max_z
            }
        return pozycje_dict
    except Exception as e:
        print(f"⚠️ Błąd SQL w Skanerze: {e}")
        return {}

def czy_na_czarnej_liscie(symbol):
    try:
        data_graniczna = (datetime.now() - timedelta(days=BAN_DNI)).timestamp()
        query = """
            SELECT count(*) FROM historia_transakcji 
            WHERE symbol = ? 
            AND zysk_proc < -0.1 
            AND (czas_wyjscia > ? OR czas_wyjscia IS NULL)
        """
        db.cursor.execute(query, (symbol, data_graniczna))
        count = db.cursor.fetchone()[0]
        if count > 0: return True
        return False
    except Exception as e:
        return False

# ==============================================================================
# 🚀 GŁÓWNA PĘTLA (WOJNA)
# ==============================================================================
def main():
    cooldowny = {} 
    ostatni_skan_rynku = 0
    historia_cen = {} 
    cache_szumu = {} # 🧠 Pamięć foteli
    
    CZARNA_LISTA_HARD = ["USDC", "FDUSD", "USDP", "TUSD", "BUSD", "EUR", "DAI"] 

    print("=" * 70)
    print(f"🚀 SKANER 3.0 (AUTO-ADAPTACJA + PASOŻYT WIELORYBA) START")
    print("=" * 70)

    while True:
        konfig = pobierz_konfiguracje()
        teraz_ts = time.time()
        teraz_str = datetime.now().strftime("%H:%M:%S")
        
        dane = get_binance_prices()
        if not dane:
            time.sleep(5)
            continue

        for sym, dt in dane.items():
            try:
                if float(dt['quoteVolume']) > MIN_VOL_24H and float(dt['lastPrice']) > MIN_CENA:
                    oblicz_przyspieszenie(sym, float(dt['lastPrice']))
            except: pass

        cooldowny = {k: v for k, v in cooldowny.items() if v > teraz_ts}
        
        # ==================================================================
        # 🛡️ ZARZĄDZANIE POZYCJĄ (AUTO-FOTELE)
        # ==================================================================
        moje = pobierz_pozycje_skanera_z_bazy()
        
        for sym, info in moje.items():
            if sym in cooldowny: continue
            if sym not in dane: continue

            act = float(dane[sym]['lastPrice'])
            cena_wejscia = info['cena_wejscia']
            zm = ((act - cena_wejscia) / cena_wejscia) * 100
            
            max_z = info.get('max_zysk', 0.0)
            if zm > max_z:
                max_z = zm
                db.aktualizuj_max_zysk(info['unikalne_id'], max_z)
            
            czas_trwania = int((teraz_ts - info.get('czas_zakupu', teraz_ts)) / 60)
            akcja = None
            powod = ""
            
            # --- OBLICZANIE SZUMU ---
            if sym not in cache_szumu or teraz_ts - cache_szumu[sym]['ts'] > 300: # Odświeża pasy co 5 min
                cache_szumu[sym] = {'szum': zmierz_szum(sym), 'ts': teraz_ts}
            
            szum = cache_szumu[sym]['szum']
            
            # 🔥 Dynamiczne ramy cięcia:
            stop_loss_limit = - (szum * 1.8)
            stop_loss_limit = max(stop_loss_limit, -5.0) # Twarda podłoga, zeby nie zbankrutować
            
            be_trigger = szum * 1.5
            trail_trigger = szum * 2.5
            trail_drop = szum * 1.0
            moon_trigger = szum * 5.0
            moon_drop = szum * 1.8

            # --- 1. ŻELAZNA TARCZA (DYNAMIC STOP LOSS) ---
            if zm <= stop_loss_limit: 
                akcja, powod = "STOP LOSS", f"Adaptacyjny SL (Strata {zm:.2f}%)"
            
            # --- 2. BIERZ CO DAJĄ ---
            elif max_z >= trail_trigger and max_z < moon_trigger and zm < (max_z - trail_drop):
                akcja, powod = "TRAILING", f"Wytrzepanie (Spadek z {max_z:.2f}%)"
                
            # --- 3. MOON TRAIL ---
            elif max_z >= moon_trigger and max_z < 25.0 and zm < (max_z - moon_drop):
                akcja, powod = "MOON-TRAIL", f"Koniec rajdu (Spadek z {max_z:.2f}%)"
                
            # 🔥 CHWYTANIE ZA GARDŁO (Sztywne, nie bawimy sie w szum przy gigantycznych zyskach)
            elif max_z >= 25.0 and zm < (max_z - 3.0):
                akcja, powod = "HARD TAKE PROFIT", f"Wycofanie na szczycie (Zysk {zm:.2f}%)"
            
            # --- 4. EWAKUACJA Z MARTWEGO PUNKTU ---
            elif max_z >= be_trigger and zm <= 0.2:
                akcja, powod = "BREAK EVEN", "Zabezpieczenie na zero"
                
            elif czas_trwania >= 12 and zm < 1.0: 
                akcja, powod = "STAGNATION", "Brak paliwa (12min)"
                
            elif czas_trwania >= 60: 
                akcja, powod = "TIMEOUT", "Wycofanie oddziału (1h)"

            # --- EGZEKUCJA ---
            if akcja:
                zysk = pm.zwroc_srodki(sym, act, zrodlo="SKANER", typ_strategii="skalp")
                kol = "🟢" if zysk > 0 else "🔴"
                print(f"⚡ {teraz_str} | {sym} | {akcja} ({powod}) | Wynik: {kol} {zysk:.2f} USDT | Max: {max_z:.2f}%")
                cooldowny[sym] = teraz_ts + COOLDOWN_CZAS
                print(f"   ❄️ {sym} oznaczony jako skażony na 30 min.")

        # ==================================================================
        # 🔭 RADAR (SKANOWANIE RYNKU I ATAK)
        # ==================================================================
        if teraz_ts - ostatni_skan_rynku >= INTERVAL_SKANOWANIA_NOWYCH:
            moje = pobierz_pozycje_skanera_z_bazy()
            moje_aktywne = {k: v for k, v in moje.items() if k not in cooldowny}
            moje_cnt = len(moje_aktywne)
            
            wolne_total = MAX_POZYCJI_SKANERA - moje_cnt
            
            total = pm.oblicz_wartosc_total()            
            zysk_tot = total - 1000.00
            kol = "🟢" if zysk_tot >= 0 else "🔴"

            print(f"\n⏰ {teraz_str} | 🔄 SKAN: {konfig['NAZWA']} | Total: {total:.2f}$ ({kol}{zysk_tot:+.2f}) | Sloty: {moje_cnt}/{MAX_POZYCJI_SKANERA}")
            
            if moje_aktywne:
                print(f"   💼 ODDZIAŁY NA FRONCIE:")
                for sym, info in moje_aktywne.items():
                    if sym in dane:
                        act = float(dane[sym]['lastPrice'])
                        zm = ((act - info['cena_wejscia']) / info['cena_wejscia']) * 100
                        czas = int((teraz_ts - info.get('czas_zakupu', teraz_ts)) / 60)
                        kol_poz = "🟢" if zm > 0 else "🔴"
                        print(f"      👉 {sym:<10} | {kol_poz} {zm:+.2f}% | Czas: {czas} min")

            wszystkie_ruchy = []
            for sym, dt in dane.items():
                try:
                    base_symbol = sym.replace("USDT", "")
                    if sym in CZARNA_LISTA_HARD or base_symbol in CZARNA_LISTA_HARD: continue

                    c = float(dt['lastPrice'])
                    v = float(dt['quoteVolume'])
                    if v < MIN_VOL_24H or c < MIN_CENA: continue
                    prev = historia_cen.get(sym, c)
                    zm = ((c - prev) / prev) * 100
                    historia_cen[sym] = c 
                    
                    if zm > 0.5: wszystkie_ruchy.append({'s': sym, 'z': zm, 'c': c, 'v': v})
                except: continue
            
            wszystkie_ruchy.sort(key=lambda x: x['z'], reverse=True)
            
            if wszystkie_ruchy:
                print(f"   🔍 POTENCJALNE CELE (Top 3 skoki):")
                for t in wszystkie_ruchy[:3]:
                    acc = oblicz_przyspieszenie(t['s'], t['c'])
                    rsi, vol_ratio, _, _ = zwiad_bojowy(t['s'])
                    print(f"      👉 {t['s']:<10} | +{t['z']:>5.2f}% | Acc: {acc:>5.2f} | RSI: {rsi:>2.0f} | Vol: {vol_ratio:>3.1f}x")
            else:
                print("   💤 Cisza na froncie (brak skoków > 0.5%)")
            
            if wolne_total > 0:
                kandydaci = []
                for k in wszystkie_ruchy:
                    if k['s'] in cooldowny or k['s'] in moje: continue
                    if k['z'] > 7.5: continue 

                    if k['z'] >= konfig['PRÓG']:
                        acc = oblicz_przyspieszenie(k['s'], k['c'])
                        if acc < PROG_ACCEL: continue
                        if czy_na_czarnej_liscie(k['s']): continue

                        # 1. Zwiad 1M
                        rsi, vol_ratio, pole_minowe, raport_zwiadu = zwiad_bojowy(k['s'])
                        if pole_minowe:
                            print(f"      🧨 ODRZUCONO {k['s']} (+{k['z']:.1f}%): {raport_zwiadu}")
                            continue

                        # 2. MICRO-SKANER TRANSAKCJI
                        pulapka, raport_micro = badanie_presji_transakcji(k['s'])
                        if pulapka:
                            print(f"      🧨 ODRZUCONO {k['s']} (+{k['z']:.1f}%): {raport_micro}")
                            continue

                        decyzja = False
                        powod = ""

                        # 🔥 BLOKADA NA BOTY WIELORYBÓW (PUMP & DUMP) - Nie wchodzimy na puste sztuczne pompy
                        if vol_ratio > MAX_VOL_RATIO:
                            decyzja, powod = False, f"Zbyt duża anomalia (Vol > {MAX_VOL_RATIO}x) - Sztuczna pompa!"
                        elif rsi < konfig['RSI']:
                            decyzja, powod = True, f"Czysty rajd (RSI {rsi:.0f})"
                        elif rsi < 95 and vol_ratio >= 2.5:
                            decyzja, powod = True, f"Agresywna pompa (RSI {rsi:.0f}, Vol x{vol_ratio:.1f})"

                        if decyzja:
                            kandydaci.append({**k, 'r': rsi, 'vr': vol_ratio, 'acc': acc, 'reason': powod})
                
                if kandydaci:
                    print("-" * 70)
                    
                    ilosc_okazji = len(kandydaci)
                    limit_tej_tury = MAX_KUPNO_NA_SKAN
                    
                    if ilosc_okazji >= FILTR_PANIKI_AKTYWACJA:
                        print(f"   ⚠️ WYKRYTO SZTUCZNĄ POMPĘ RYNKOWĄ ({ilosc_okazji} celów). Biorę tylko {FILTR_PANIKI_LIMIT} najlepszych.")
                        limit_tej_tury = FILTR_PANIKI_LIMIT
                    
                    limit_ostateczny = min(wolne_total, limit_tej_tury)
                    do_kupienia = kandydaci[:limit_ostateczny]
                    
                    for k in do_kupienia:
                        sukces, il, koszt = pm.pobierz_srodki(k['s'], k['c'], 0.07, "SKANER", "skalp")
                        if sukces:
                            print(f"🔥 {k['s']:<10} | +{k['z']:.2f}% | {k['reason']} | Acc: {k['acc']:.2f} | ATAKUJĘ")
                        else:
                            print(f"⚠️ {k['s']} | BRAK AMUNICJI W PORTFELU")
                    
                    if len(kandydaci) > limit_ostateczny:
                        print(f"   ℹ️ Utrzymano dyscyplinę: zaatakowano {limit_ostateczny} celów.")

                else:
                    print(f"   ⛔ Brak czystych celów (Wymogi: Wzrost > {konfig['PRÓG']}%, Czysty wykres 1m, Czysty Orderbook).")
            else:
                print("⛔ Oddziały w pełni rozdysponowane (10/10).")

            print(f"\n💤 Zwiad zakończony. Czekam 5 minut...")
            ostatni_skan_rynku = teraz_ts

        time.sleep(INTERVAL_OCHRONY)

if __name__ == "__main__":
    main()