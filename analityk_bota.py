import json
from datetime import datetime
from ai_helper import ask_ai
import re
import hashlib
# Importujemy nasz naprawiony utils
from utils_data import extract_ohlc, analizuj_swiece
from strategia_helper import extract_knowledge_as_dict, save_strategies, save_lessons

MOZG_PATH = "mozg.json"
RYNEK_PATH = "rynek.json"

main_symbols = ["BTC", "ETH", "SOL"]

def load_brain():
    try:
        with open(MOZG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"lessons": [], "strategies": []}

def load_market_data():
    try:
        with open(RYNEK_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def evaluate_lessons(lessons):
    """
    Naprawiona logika oceniania. Sprawdza kierunek zamiast liczb.
    """
    for lesson in lessons:
        if lesson.get("success") is not None:
            continue # Już ocenione

        # Pobieramy co AI przewidziało (tekst) i co się stało (liczba)
        # UWAGA: To zadziała, jeśli w 'mozg_bota' lub 'bot_evaluator' dodasz 'actual_change' do lekcji po czasie.
        # Jeśli tego nie ma, ta funkcja tylko przygotowuje pole.
        
        tekst_ai = lesson.get("ai_response", "").lower()
        actual_change = lesson.get("actual_change", 0)

        # Prosta heurystyka
        if "wzrost" in tekst_ai or "buy" in tekst_ai or "long" in tekst_ai:
            if actual_change > 0.1: lesson["success"] = True
            elif actual_change < -0.1: lesson["success"] = False
        
        elif "spadek" in tekst_ai or "sell" in tekst_ai or "short" in tekst_ai:
            if actual_change < -0.1: lesson["success"] = True
            elif actual_change > 0.1: lesson["success"] = False

    return lessons

def build_self_analysis_prompt(lessons, data, symbols):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    prices = data.get("prices", [])
    
    # 1. Budowanie sekcji z wykresem (NOWOŚĆ z utils_data)
    candle_analysis_text = ""
    for sym in symbols:
        # Próbujemy znaleźć świece dla symbolu (np. BTCUSDT)
        # Dodajemy 'USDT' bo tak zwykle są w pliku rynek.json
        ohlc = extract_ohlc(data, sym) 
        analiza = analizuj_swiece(ohlc)
        candle_analysis_text += f"\n--- {sym} ---\n{analiza}\n"

    # 2. Budowanie sekcji lekcji (Co działało, a co nie)
    recent_lessons = lessons.get("lessons", [])[-5:] # Ostatnie 5 lekcji
    lesson_summaries = ""
    if recent_lessons:
        lesson_summaries = "MOJE OSTATNIE DOŚWIADCZENIA (Ucz się z tego!):\n"
        for i, l in enumerate(recent_lessons):
            status = "NIEOCENIONE"
            if l.get("success") is True: status = "SUKCES (Powtórz to!)"
            if l.get("success") is False: status = "PORAŻKA (Unikaj tego!)"
            lesson_summaries += f"Lekcja {i+1} [{status}]: {l.get('ai_response')[:200]}...\n"
    else:
        lesson_summaries = "Brak wcześniejszych lekcji. Zaczynamy naukę."

    prompt = (
        f"Jesteś algorytmicznym botem inwestycyjnym Pro-Trader. Twoim celem jest NAUKA i zysk.\n"
        f"Data: {today}\n\n"
        f"{lesson_summaries}\n\n"
        f"DANE RYNKOWE I TECHNICZNE (Analiza świec):\n"
        f"{candle_analysis_text}\n\n"
        "Twoje zadania:\n"
        "1. Przeanalizuj technicznie wykresy (Price Action).\n"
        "2. Wyciągnij wnioski z poprzednich lekcji (unikaj błędów).\n"
        "3. Wygeneruj strategie w formacie JSON.\n\n"
        "WAŻNE: Odpowiedź musi zawierać JSON z strategiami na końcu.\n"
        "Format JSON (przykład):\n"
        "[\n"
        "  {\n"
        "    \"Nazwa\": \"Wybicie BTC\",\n"
        "    \"Opis\": \"Short squeeze na wysokim wolumenie\",\n"
        "    \"Symbol\": \"BTC\",\n"
        "    \"Typ\": \"kupno\",\n"
        "    \"Warunek\": \"Cena > średnia z 5 świec\",\n"
        "    \"Oczekiwany ruch\": \"wzrost\",\n"
        "    \"Pewność\": \"wysoka\",\n"
        "    \"Stosuj gdy\": \"zmienność jest niska\"\n"
        "  }\n"
        "]\n"
    )
    return prompt

def get_symbols_to_analyze(market_data):
    # Prosta wersja - bierze główne + co tam znajdzie w ohlc
    base = ["BTC", "ETH", "SOL"]
    found = []
    if "ohlc" in market_data:
        found = [k.replace("USDT","") for k in market_data["ohlc"].keys()]
    return list(set(base + found))

# ... (reszta funkcji pomocniczych jak get_strategy_hash bez zmian) ...

def save_knowledge(strategies, lekcje):
    # To zostawiamy bez zmian - jest OK, pod warunkiem, że extract działa
    try:
        with open("strategie.json", "r", encoding="utf-8") as f:
            existing = json.load(f)
    except:
        existing = []

    # Dodajemy tylko unikalne (prosta logika)
    existing.extend(strategies) 
    
    # Zapisz strategie
    with open("strategie.json", "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=4, ensure_ascii=False)

    # Zapisz lekcje
    if lekcje:
        try:
            with open("lekcje.json", "r", encoding="utf-8") as f:
                old_lessons = json.load(f)
        except:
            old_lessons = []
            
        old_lessons.extend(lekcje)
        with open("lekcje.json", "w", encoding="utf-8") as f:
            json.dump(old_lessons, f, indent=4, ensure_ascii=False)
            
    print(f"✅ Zapisano wiedzę: {len(strategies)} strategii, {len(lekcje)} lekcji.")

def main():
    brain = load_brain()
    market_data = load_market_data()

    symbols = get_symbols_to_analyze(market_data)
    prompt = build_self_analysis_prompt(brain, market_data, symbols)

    print("📤 Analizuję rynek i historię...")
    response = ask_ai(prompt)
    
    if response:
        print("🧠 Wnioski AI otrzymane.")
        
        # Zapisz surową odpowiedź jako lekcję 'do oceny'
        brain.setdefault("lessons", [])
        brain["lessons"].append({
            "prompt": prompt,
            "ai_response": response,
            "date": datetime.utcnow().isoformat(),
            "success": None, # Czeka na ocenę przez bot_evaluator
            "actual_change": 0 # To uzupełni bot_evaluator po czasie
        })

        # Wyciąganie JSON ze środka tekstu (Naprawione regexem w helperze)
        knowledge = extract_knowledge_as_dict(response)
        strategies = knowledge.get("strategies", [])
        lekcje_z_tresci = knowledge.get("edukacja", {}).get("zalecenia", [])

        save_strategies(strategies)
        if lekcje_z_tresci:
            save_lessons(lekcje_z_tresci)

        # Zapisz stan mózgu
        with open(MOZG_PATH, "w", encoding="utf-8") as f:
            json.dump(brain, f, indent=2, ensure_ascii=False)
            
if __name__ == "__main__":
    main()