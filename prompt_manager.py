import json
import random
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

# ---- KONFIGURACJA PROMPTÓW (NOWE - TECHNICZNE) ----
PROMPT_TEMPLATES = [
    "Jesteś doświadczonym traderem Price Action. Spójrz na dostarczone dane świecowe (OHLC) i oceń trend dla ostatnich {timeframe}. Czy widzisz formacje odwrócenia lub kontynuacji?",
    "Jako analityk techniczny, zignoruj szum medialny. Skup się tylko na liczbach: Zmienność, Wolumen, Trend. Co mówią dane z ostatnich {timeframe}?",
    "Twoim zadaniem jest ochrona kapitału. Przeanalizuj ryzyko na podstawie zmienności z ostatnich {timeframe}. Czy rynek jest bezpieczny do wejścia?",
    "Szukaj anomalii w wolumenie w perspektywie {timeframe}. Czy ostatnie ruchy ceny są potwierdzone przez wolumen? Podaj zwięzłą diagnozę."
]

TIMEFRAMES = ["50 godzin", "50 świec", "ostatniej doby"]
STATE_FILE = Path("state.json")

# ---- HELPERS DO STANU ----
def load_state() -> dict:
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except: pass
    return {"timeframe_index": 0}

def save_state(state: dict) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except: pass

def get_next_prompt() -> str:
    """Rotuje prompty skupione na analizie technicznej"""
    state = load_state()
    idx = int(state.get("timeframe_index", 0))
    
    template = random.choice(PROMPT_TEMPLATES)
    timeframe = TIMEFRAMES[idx % len(TIMEFRAMES)]
    
    state["timeframe_index"] = (idx + 1) % len(TIMEFRAMES)
    save_state(state)
    
    return template.format(timeframe=timeframe)

# ---- FUNKCJE POMOCNICZE (TEGO BRAKOWAŁO!) ----

def safe_json_parse(s: str) -> Any:
    """Próba bezpiecznego sparsowania JSONa"""
    if not s: return None
    try:
        # Czasami AI dodaje markdown ```json ... ```
        clean = s.strip()
        if "```" in clean:
            clean = clean.split("```json")[-1].split("```")[0]
        return json.loads(clean.strip())
    except Exception:
        return None

def build_strict_strategy_prompt(
    market_snapshot: Dict[str, Any],
    recent_agent_actions: Optional[List[Dict[str, Any]]] = None,
    memory_snippets: Optional[List[str]] = None,
    timeframe: str = "1 godziny",
    required_fields: Optional[List[str]] = None,
) -> str:
    """Buduje prompt wymuszający JSON"""
    if required_fields is None:
        required_fields = ["name", "rationale", "entry_conditions", "risk_level"]

    prompt = f"""
    Na podstawie danych rynkowych wygeneruj strategię tradingową w formacie JSON.
    Timeframe: {timeframe}
    
    Wymagane pola JSON: {required_fields}
    Odpowiedź ma być CZYSTYM kodem JSON, bez komentarzy.
    """
    return prompt

def build_analysis_prompt(
    market_snapshot: Dict[str, Any],
    question_focus: str = "analiza techniczna",
    max_bullets: int = 5
) -> str:
    """Buduje prompt analityczny"""
    return f"Przeanalizuj te dane pod kątem: {question_focus}. Wypisz max {max_bullets} punktów."

def build_validation_prompt(expected_schema: Dict[str, Any], candidate_strategy_json: str) -> str:
    """Prompt do walidacji (opcjonalny, zostawiamy dla kompatybilności)"""
    return f"Sprawdź czy ten JSON pasuje do schematu: {candidate_strategy_json}"
    