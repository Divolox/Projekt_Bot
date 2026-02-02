import json

dane_startowe = {
    "saldo_gotowka": 1000.00,       # Twoje wirtualne 1000 USDT
    "wartosc_total": 1000.00,
    "historia_transakcji": 0,
    "pozycje": {}                   # Pusty portfel na start
}

with open("portfel.json", "w") as f:
    json.dump(dane_startowe, f, indent=2)

print("✅ portfel.json został utworzony w Folderze Głównym! Gotowe.")

