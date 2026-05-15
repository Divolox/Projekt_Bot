import requests
import time
import sys
import os
from datetime import datetime, timedelta

# ==============================================================================
# 🚀 SKANER 4.1 + MATADOR (ORDER BOOK X-RAY) + SPREAD SHIELD
# ==============================================================================

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

# --- KONFIGURACJA STRATEGII ---
MIN_VOL_24H = 450000 
MIN_CENA = 0.00001 

MAX_POZYCJI_SKANERA = 10   
MAX_KUPNO_NA_SKAN = 8      
FILTR_PANIKI_AKTYWACJA = 10  
FILTR_PANIKI_LIMIT = 5       

INTERVAL_SKANOWANIA_NOWYCH = 300 
INTERVAL_OCHRONY = 5  
COOLDOWN_CZAS = 1800      

CFG_RSI = 85
CFG_RSI_NIEDZIELA = 75

BAN_DNI = 3      
PROG_ACCEL = 0.0 
MIN_VOL_MULTI = 0.5 
MAX_VOL_RATIO = 15.0 

historia_cen_local = {} 

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

        ostatni_vol = volumes[-1]
        sredni_vol = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else 1
        vol_ratio = ostatni_vol / sredni_vol if sredni_vol > 0 else 1.0

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
# 🧠 MICRO-SKANER TRANSAKCJI
# ==============================================================================
def badanie_presji_transakcji(symbol):
    try:
        url = f"https://api.binance.com/api/v3/trades?symbol={symbol}&limit=500"
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
        
        if procent_kupna < 20.0:
            return True, f"PUŁAPKA (Agresywna sprzedaż: {100-procent_kupna:.0f}%)"
        else:
            return False, f"CZYSTO (Presja kupna: {procent_kupna:.0f}%)"

    except Exception as e:
        return False, "Brak danych z orderbooka"

# ==============================================================================
# 🛡️ NOWOŚĆ: MATADOR (SKANER PANCERZA ORDER BOOK)
# ==============================================================================
def skaner_pancerza(symbol, current_price):
    try:
        url = f"https://api.binance.com/api/v3/depth?symbol={symbol}&limit=100"
        resp = requests.get(url, timeout=5).json()
        
        bids = resp.get('bids', [])
        asks = resp.get('asks', [])
        
        if not bids or not asks:
            return False, "Brak danych z Order Booka"
            
        # Skanujemy 1.5% w dół (Wsparcie) i 1.5% w górę (Opór)
        dolna_granica = current_price * 0.985
        gorna_granica = current_price * 1.015
        
        vol_wsparcia = 0.0
        for b in bids:
            price = float(b[0])
            qty = float(b[1])
            if price >= dolna_granica:
                vol_wsparcia += (price * qty)
            else:
                break # Bids są posortowane malejąco
                
        vol_oporu = 0.0
        for a in asks:
            price = float(a[0])
            qty = float(a[1])
            if price <= gorna_granica:
                vol_oporu += (price * qty)
            else:
                break # Asks są posortowane rosnąco
                
        if vol_wsparcia == 0: vol_wsparcia = 1.0 
        
        stosunek = vol_oporu / vol_wsparcia
        
        # 1. Sprawdzamy czy przed nami nie ma betonowej ściany (3x więcej kapitału na sprzedaż)
        if stosunek > 3.0:
            return True, f"BETONOWA ŚCIANA (Sprzedaż {stosunek:.1f}x większa od wsparcia)"
            
        # 2. Sprawdzamy, czy pod spodem nie ma przepaści (Rug pull check)
        if vol_wsparcia < 5000.0:
            return True, f"PRZEPAŚĆ (Puste wsparcie pod ceną, tylko {vol_wsparcia:.0f}$)"
            
        return False, f"WSPARCIE OK (Stosunek {stosunek:.1f}x)"
    except Exception as e:
        return False, "Błąd skanera pancerza"

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
    
    CZARNA_LISTA_HARD = ["USDC", "FDUSD", "USDP", "TUSD", "BUSD", "EUR", "DAI"] 

    print("=" * 70)
    print(f"🚀 SKANER 4.1 + MATADOR (ORDER BOOK X-RAY) START")
    print("=" * 70)

    while True:
        teraz_ts = time.time()
        teraz_str = datetime.now().strftime("%H:%M:%S")
        
        limit_rsi = CFG_RSI_NIEDZIELA if datetime.today().weekday() == 6 else CFG_RSI
        
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
        # 🛡️ ZARZĄDZANIE POZYCJĄ (ORYGINALNE)
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

            if zm <= -0.8:
                akcja, powod = "STOP LOSS", f"Twarde cięcie (Strata {zm:.2f}%)"

            elif max_z >= 0.6 and zm <= 0.1:
                akcja, powod = "BREAK EVEN", "Szybka ewakuacja na zero"

            elif max_z >= 1.5 and max_z < 3.0 and zm < (max_z - 0.5):
                akcja, powod = "ZYSK", f"Krótka smycz (Spadek z {max_z:.2f}%)"

            elif max_z >= 3.0 and max_z < 8.0 and zm < (max_z - 0.8):
                akcja, powod = "TRAILING", f"Agresywny cień (Spadek z {max_z:.2f}%)"

            elif max_z >= 8.0 and max_z < 25.0 and zm < (max_z - 1.5):
                akcja, powod = "MOON-TRAIL", f"Koniec rajdu (Spadek z {max_z:.2f}%)"

            elif max_z >= 25.0 and zm < (max_z - 3.0):
                akcja, powod = "HARD TAKE PROFIT", f"Wycofanie na szczycie (Zysk {zm:.2f}%)"

            elif czas_trwania >= 8 and zm < 0.3:
                akcja, powod = "STAGNATION", "Brak szybkiego zapłonu (8min)"

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
            
            skoki_powyzej_1 = sum(1 for k in wszystkie_ruchy if k['z'] >= 1.0)
            
            if datetime.today().weekday() == 6:
                dynamiczny_prog = 2.8
                stan_rynku_opis = f"🛡️ PATROL (Niedziela) | Aktywne pompy >1%: {skoki_powyzej_1} | Próg: {dynamiczny_prog}%"
            elif skoki_powyzej_1 >= 15:
                dynamiczny_prog = 2.0
                stan_rynku_opis = f"🔥 ZIELONY FRONT (Mocny trend) | Aktywne pompy >1%: {skoki_powyzej_1} | Próg: {dynamiczny_prog}%"
            elif skoki_powyzej_1 >= 5:
                dynamiczny_prog = 2.4
                stan_rynku_opis = f"⚠️ SZUM RYNKOWY (Umiarkowana siła) | Aktywne pompy >1%: {skoki_powyzej_1} | Próg: {dynamiczny_prog}%"
            else:
                dynamiczny_prog = 2.8
                stan_rynku_opis = f"💀 RZEŹNIA (Brak paliwa na rynku) | Aktywne pompy >1%: {skoki_powyzej_1} | Próg: {dynamiczny_prog}%"

            print(f"\n⏰ {teraz_str} | 🔄 SKAN: {stan_rynku_opis}")
            print(f"   💰 Total: {total:.2f}$ ({kol}{zysk_tot:+.2f}) | Sloty: {moje_cnt}/{MAX_POZYCJI_SKANERA}")
            
            if moje_aktywne:
                print(f"   💼 ODDZIAŁY NA FRONCIE:")
                for sym, info in moje_aktywne.items():
                    if sym in dane:
                        act = float(dane[sym]['lastPrice'])
                        zm = ((act - info['cena_wejscia']) / info['cena_wejscia']) * 100
                        czas = int((teraz_ts - info.get('czas_zakupu', teraz_ts)) / 60)
                        kol_poz = "🟢" if zm > 0 else "🔴"
                        print(f"      👉 {sym:<10} | {kol_poz} {zm:+.2f}% | Czas: {czas} min")
            
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

                    if k['z'] >= dynamiczny_prog:
                        acc = oblicz_przyspieszenie(k['s'], k['c'])
                        if acc < PROG_ACCEL: continue
                        if czy_na_czarnej_liscie(k['s']): continue

                        # --- NOWOŚĆ: UKRYTY ZABÓJCA (SKANER SPREADU) ---
                        sym_dane = dane[k['s']]
                        bid = float(sym_dane['bidPrice'])
                        ask = float(sym_dane['askPrice'])
                        spread = ((ask - bid) / bid) * 100 if bid > 0 else 0.0
                        
                        if spread > 0.4:
                            print(f"      🧨 ODRZUCONO {k['s']} (+{k['z']:.1f}%): Za duży spread ({spread:.2f}%)")
                            continue

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
                            
                        # 3. NOWOŚĆ: MATADOR (ORDER BOOK X-RAY)
                        pulapka_ob, raport_ob = skaner_pancerza(k['s'], k['c'])
                        if pulapka_ob:
                            print(f"      🧨 ODRZUCONO {k['s']} (+{k['z']:.1f}%): {raport_ob}")
                            continue

                        decyzja = False
                        powod = ""

                        # 🔥 BLOKADA NA BOTY WIELORYBÓW I PUSTE POMPY
                        if vol_ratio > MAX_VOL_RATIO:
                            decyzja, powod = False, f"Zbyt duża anomalia (Vol > {MAX_VOL_RATIO}x) - Sztuczna pompa!"
                        elif vol_ratio < MIN_VOL_MULTI:
                            decyzja, powod = False, f"Pusta pompa (Vol < {MIN_VOL_MULTI}x) - Brak paliwa!"
                        elif rsi < limit_rsi:
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
                    print(f"   ⛔ Brak czystych celów (Wymogi: Wzrost > {dynamiczny_prog}%, Czysty wykres 1m, Czysty Orderbook).")
            else:
                print("⛔ Oddziały w pełni rozdysponowane (10/10).")

            print(f"\n💤 Zwiad zakończony. Czekam 5 minut...")
            ostatni_skan_rynku = teraz_ts

        time.sleep(INTERVAL_OCHRONY)

if __name__ == "__main__":
    main()