import json
import os
from pathlib import Path

PLIK = "strategie_bota.json"

def zapisz_strategie_bota(nowa_strategia):
    if Path(PLIK).exists():
        with open(PLIK, "r", encoding="utf-8") as f:
            strategie = json.load(f)
    else:
        strategie = []

    # Upewnij się, że nowa strategia ma status
    if "status" not in nowa_strategia:
        nowa_strategia["status"] = "oczekuje"

    strategie.append(nowa_strategia)

    with open(PLIK, "w", encoding="utf-8") as f:
        json.dump(strategie, f, indent=4, ensure_ascii=False)

def wczytaj_strategie_bota():
    if not os.path.exists(PLIK):
        return []
    with open(PLIK, "r", encoding="utf-8") as f:
        return json.load(f)

def zaktualizuj_strategie_bota(zmieniona):
    strategie = wczytaj_strategie_bota()
    for i, s in enumerate(strategie):
        if s.get("id") == zmieniona.get("id"):
            strategie[i] = zmieniona
            break
    with open(PLIK, "w", encoding="utf-8") as f:
        json.dump(strategie, f, indent=2, ensure_ascii=False)
