import subprocess
import time
import sys
import os
from datetime import datetime, timedelta  # <--- WAŻNE: Dodano timedelta

# ==========================================
# ⚙️ KONFIGURACJA
# ==========================================
INTERVAL_STRATEGII = 3600  # Mózg co 1h (limit zapytań AI)
INTERVAL_KONTROLI = 300    # Ewaluator co 5 min (bezpieczeństwo)
# ==========================================

def uruchom_skrypt(nazwa_pliku):
    """Uruchamia zewnętrzny skrypt i czeka na jego zakończenie"""
    try:
        if not os.path.exists(nazwa_pliku):
            print(f"⚠️ BŁĄD: Brak pliku {nazwa_pliku}")
            return
        # Uruchamiamy proces
        subprocess.run([sys.executable, nazwa_pliku], check=True)
    except Exception as e:
        print(f"⚠️ Błąd uruchamiania {nazwa_pliku}: {e}")

def czekaj_do_pelnej_minuty(minuty=5):
    """
    NAPRAWIONA WERSJA: Obsługuje przejście przez północ (23:59 -> 00:00).
    Używa timedelta zamiast prostego dodawania godzin.
    """
    teraz = datetime.now()
    
    # Obliczamy ile minut brakuje do pełnego interwału
    # Np. jest 14:03, interwał 5 -> brakuje 2 minut do 14:05
    minuty_do_czekania = minuty - (teraz.minute % minuty)
    
    # Dodajemy ten czas do "teraz" (to bezpieczne, system sam zmieni dzień jak trzeba)
    cel = (teraz + timedelta(minutes=minuty_do_czekania)).replace(second=0, microsecond=0)
    
    delta = (cel - teraz).total_seconds()
    
    # Zabezpieczenie (gdyby obliczenia trwały ułamek sekundy za długo)
    if delta < 0: 
        delta += minuty * 60
    
    print(f"💤 Synchronizacja... Czekam {delta:.0f}s do {cel.strftime('%H:%M:%S')}")
    time.sleep(delta)

def main():
    print(f"🚀 SYSTEM START: Orchestrator Modułowy (Fix Północy)")
    ostatnia_generacja = 0

    while True:
        teraz = time.time()
        teraz_str = datetime.now().strftime("[%H:%M]")
        
        print(f"\n⏱️ {teraz_str} --- CYKL KONTROLNY ---")

        # 1. ZAWSZE: Obserwator (pobiera dane)
        uruchom_skrypt("botobserwator.py")

        # 2. ZAWSZE: Ewaluator (zamyka pozycje/tnie straty)
        uruchom_skrypt("bot_evaluator.py")

        # 3. RAZ NA GODZINĘ: Mózg (szuka okazji)
        if teraz - ostatnia_generacja >= INTERVAL_STRATEGII:
            print(f"🧠 {teraz_str} Uruchamiam Mózg...")
            uruchom_skrypt("mozg_bota.py")
            
            # Scheduler (jeśli istnieje, otwiera pozycje z mózgu)
            if os.path.exists("bot_scheduler.py"):
                uruchom_skrypt("bot_scheduler.py")
            
            ostatnia_generacja = time.time()
        
        # 4. Synchronizacja (Pancerna wersja)
        czekaj_do_pelnej_minuty(5)

if __name__ == "__main__":
    main()

