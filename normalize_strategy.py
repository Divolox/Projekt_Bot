# normalize_strategies.py  (uruchom raz)
import json, datetime
from pathlib import Path

SRC = Path("strategie_bota.json")
if not SRC.exists():
    print("Nie znaleziono strategie_bota.json")
    raise SystemExit(1)

with open(SRC, "r", encoding="utf-8") as f:
    strategie = json.load(f)

TYPE_ALIASES = {"godzinowa":"godzinowa","1h":"godzinowa","hourly":"godzinowa",
                "jednodniowa":"jednodniowa","dzienna":"jednodniowa","1d":"jednodniowa",
                "tygodniowa":"tygodniowa","1w":"tygodniowa","weekly":"tygodniowa"}

def norm_typ(raw):
    if not raw: return "godzinowa"
    r = str(raw).lower()
    if r in TYPE_ALIASES: return TYPE_ALIASES[r]
    for k,v in TYPE_ALIASES.items():
        if k in r:
            return v
    return "godzinowa"

now = datetime.datetime.now().isoformat()
changed = 0
for s in strategie:
    if "czas_utworzenia" not in s:
        s["czas_utworzenia"] = s.get("data_utworzenia", now)
        changed += 1
    if "status" not in s:
        s["status"] = "oczekuje"
        changed += 1
    if "typ" not in s:
        s["typ"] = norm_typ(s.get("rodzaj", None))
        changed += 1
    if "id" not in s:
        s["id"] = f"unnamed_{now}"
        changed += 1

with open(SRC, "w", encoding="utf-8") as f:
    json.dump(strategie, f, indent=4, ensure_ascii=False)

print(f"Zrobione. Poprawiono/podstawiono {changed} pól w {len(strategie)} strategiach.")
