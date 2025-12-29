import json
import time
import os

# ŚcieżKI
STRATEGIE_TEMP = "strategie.json"       # Tu Mózg wrzuca propozycje
STRATEGIE_DB = "strategie_bota.json"    # Tu jest Twoja historia i aktywne
RYNEK_PATH = "rynek.json"               # Stąd bierzemy aktualną cenę

def wczytaj_json(sciezka):
    if os.path.exists(sciezka):
        try:
            with open(sciezka, "r", encoding="utf-8") as f: return json.load(f)
        except: return [] if "strategie" in sciezka else {}
    return [] if "strategie" in sciezka else {}

def zapisz_json(sciezka, dane):
    try:
        with open(sciezka, "w", encoding="utf-8") as f: json.dump(dane, f, indent=2)
    except: pass

def main():
    print(f"🔄 SCHEDULER: Przetwarzanie zleceń...")
    
    # 1. Wczytaj dane
    nowe_propozycje = wczytaj_json(STRATEGIE_TEMP)
    baza_strategii = wczytaj_json(STRATEGIE_DB)
    rynek = wczytaj_json(RYNEK_PATH)
    
    zmiany = False
    teraz = time.time()

    # 2. NAPRAWA ZOMBIE (Te co wiszą jako "oczekuje")
    # Jeśli coś wisi w bazie jako "oczekuje", to musimy to popchnąć.
    for s in baza_strategii:
        if s.get('status') == 'oczekuje':
            # Sprawdź wiek strategii
            czas_utworzenia = s.get('czas_utworzenia', teraz)
            # Fix dla daty w formacie string (ISO) z jsona
            if isinstance(czas_utworzenia, str): 
                # Jeśli to stary string, to uznajemy że jest sprzed chwili, żeby ją aktywować
                # Albo po prostu olewamy wiek i aktywujemy.
                pass 
            
            print(f"   🔧 NAPRAWIAM ZOMBIE: {s['symbol']} ({s['typ']}) -> AKTYWNA")
            s['status'] = 'aktywna'
            # Aktualizujemy czas startu na TERAZ, żeby Ewaluator nie zamknął jej od razu za "time out"
            s['czas_start_ts'] = teraz 
            zmiany = True

    # 3. PRZETWARZANIE NOWYCH (Z Mózgu)
    if nowe_propozycje:
        for s in nowe_propozycje:
            sym = s['symbol']
            
            # Pobierz aktualną cenę z rynku (dla precyzji)
            cena_start = s.get('start_price') # Domyślnie to co dał mózg
            if sym in rynek.get('data', {}):
                try:
                    cena_start = rynek['data'][sym]['1h'][-1]['c']
                except: pass
            
            # Ustawiamy parametry startowe
            s['status'] = 'aktywna'  # <--- TU BYŁ BŁĄD WCZEŚNIEJ
            s['cena_start'] = cena_start
            s['czas_start_ts'] = teraz
            s['czas_utworzenia_str'] = time.strftime('%Y-%m-%d %H:%M:%S')
            
            # Sprawdź czy takiej już nie ma (żeby nie dublować)
            juz_jest = False
            for stary in baza_strategii:
                if stary.get('status') == 'aktywna' and stary['symbol'] == sym and stary['typ'] == s['typ']:
                    juz_jest = True
                    break
            
            if not juz_jest:
                print(f"   ✅ AKTYWACJA: {sym} [{s['typ']}] po cenie {cena_start}")
                baza_strategii.append(s)
                zmiany = True
            else:
                print(f"   ⚠️ Ignoruję dubel: {sym} [{s['typ']}]")

        # Wyczyść plik tymczasowy (bo już przyjęliśmy zlecenia)
        zapisz_json(STRATEGIE_TEMP, [])

    # 4. ZAPISZ WSZYSTKO
    if zmiany:
        zapisz_json(STRATEGIE_DB, baza_strategii)
        print("   💾 Baza strategii zaktualizowana.")
    else:
        print("   (Brak nowych zleceń)")

if __name__ == "__main__":
    main()

