import sys

try:
    from binance.client import Client
    from binance.exceptions import BinanceAPIException
except ImportError:
    print("❌ Brak biblioteki. Wpisz w terminalu: pip install python-binance")
    sys.exit()

# ==========================================
# 🔑 WKLEJ TUTAJ SWOJE KLUCZE Z BINANCE
# ==========================================
API_KEY = '23mgoIJkhfc0ZokGqvSxERrn1JVeJBUdDQuLx7006Nc3AbxK6xCrWEEIaH8ukIyn'
API_SECRET = 'v9ieKiMqAdD1VXSIGVsbBWsdXD8kv6MoNkXtNPK0jtK1ej3VRyWywyMSQdXne8s4'

def sprawdz_saldo():
    print("=" * 50)
    print("💰 TEST POBIERANIA SALDA Z BINANCE 💰")
    print("=" * 50)
    
    try:
        # Inicjalizacja klienta
        client = Client(API_KEY, API_SECRET)
        print("🔄 Łączenie z kontem Binance...")
        
        # Pobieramy stan USDT
        balance = client.get_asset_balance(asset='USDT')
        
        if balance:
            wolne_srodki = float(balance['free'])
            zablokowane_srodki = float(balance['locked'])
            total = wolne_srodki + zablokowane_srodki
            
            print(f"✅ POŁĄCZONO Z SUKCESEM!")
            print("-" * 50)
            print(f"💵 Całkowite USDT na koncie: {total:.2f}")
            print(f"🟢 Wolne USDT (gotowe do gry): {wolne_srodki:.2f}")
            print(f"🔒 Zablokowane USDT (np. w zleceniach): {zablokowane_srodki:.2f}")
            print("-" * 50)
            print("🚀 Bot widzi Twoją kasę i jest gotowy do rozdzielania stawek!")
        else:
            print("⚠️ Nie znaleziono portfela USDT na koncie.")

    except BinanceAPIException as e:
        print(f"\n❌ [BŁĄD BINANCE] Kod: {e.status_code}")
        print(f"Treść błędu: {e.message}")
    except Exception as e:
        print(f"\n❌ [BŁĄD SYSTEMU] Wystąpił problem: {e}")

if __name__ == "__main__":
    if API_KEY == 'TWÓJ_KLUCZ_API' or not API_KEY:
        print("⚠️ Zanim uruchomisz, wklej swoje klucze API w kodzie skryptu!")
    else:
        sprawdz_saldo()