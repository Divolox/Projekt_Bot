import json
import re

STRATEGIE_FILE = "strategie.json"

def save_strategies(strategies):
    """
    Zapisuje listę strategii do pliku JSON.
    WAŻNE: Tryb 'w' (write) całkowicie nadpisuje plik.
    Dzięki temu nie zostają stare 'Zombie' strategie.
    """
    try:
        with open(STRATEGIE_FILE, "w", encoding="utf-8") as f:
            json.dump(strategies, f, indent=2)
            # print(f"💾 Zapisano {len(strategies)} nowych propozycji.") 
    except Exception as e:
        print(f"⚠️ Błąd zapisu strategii: {e}")

def extract_knowledge(text):
    """
    Wyciąga JSON z tekstu zwróconego przez AI.
    """
    if not text: return [], "Brak odpowiedzi"
    
    # 1. Próba znalezienia bloku kodu ```json ... ```
    match = re.search(r"```json(.*?)```", text, re.DOTALL)
    if match:
        json_str = match.group(1).strip()
    else:
        # 2. Jeśli nie ma bloków, szukamy klamer [] lub {}
        match_list = re.search(r"\[.*\]", text, re.DOTALL)
        match_dict = re.search(r"\{.*\}", text, re.DOTALL)
        
        if match_list:
            json_str = match_list.group(0).strip()
        elif match_dict:
            # Jeśli AI zwróciło pojedynczy obiekt {}, pakujemy go w listę []
            json_str = "[" + match_dict.group(0).strip() + "]"
        else:
            return [], "Brak formatu JSON"

    # 3. Parsowanie
    try:
        data = json.loads(json_str)
        if isinstance(data, list):
            return data, "OK"
        elif isinstance(data, dict):
            return [data], "OK"
        else:
            return [], "Nieprawidłowa struktura JSON"
    except json.JSONDecodeError:
        return [], "Błąd dekodowania JSON"