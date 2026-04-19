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

def test_api():
    print("=" * 50)
    print("🧪 ROZPOCZYNAM TESTOWANIE POŁĄCZENIA Z BINANCE 🧪")
    print("=" * 50)
    
    try:
        print("🔄 Łączenie z giełdą...")
        client = Client(API_KEY, API_SECRET)
        
        # 1. Test ping (czy Binance w ogóle odpowiada)
        client.ping()
        print("✅ Ping: Giełda odpowiada.")
        
        # 2. Test kluczy i uprawnień (czy klucze są poprawne i mają dostęp do konta)
        print("🔄 Pobieranie statusu konta...")
        account = client.get_account()
        
        if account['canTrade']:
            print("✅ Uprawnienia: Twoje klucze mają włączoną opcję HANDLU (Spot Trading).")
        else:
            print("❌ Błąd uprawnień: Twoje klucze NIE MAJĄ włączonej opcji handlu!")
            print("   Wejdź na Binance -> Zarządzanie API -> Edytuj klucz -> Zaznacz 'Enable Spot & Margin Trading'")
            return

        # 3. Test zlecenia (Używamy create_test_order - to NIE POBIERA środków)
        print("🔄 Próba wysłania testowego zlecenia (Kupno BTC za 10 USDT)...")
        client.create_test_order(
            symbol='BTCUSDT',
            side='BUY',
            type='MARKET',
            quoteOrderQty=10.0
        )
        print("✅ Zlecenie testowe przeszło bezbłędnie! API przyjęło order.")
        
        print("\n🎉 WSZYSTKO DZIAŁA PERFEKCYJNIE. MOŻESZ ODPALAĆ BOTA NA REALNYM KAPITALE!")

    except BinanceAPIException as e:
        print(f"\n❌ [BŁĄD BINANCE] Kod: {e.status_code}")
        print(f"Treść błędu: {e.message}")
        if e.status_code == -2015:
            print("👉 Podpowiedź: Błędny klucz API, zły Secret lub klucz nie ma uprawnień.")
    except Exception as e:
        print(f"\n❌ [BŁĄD SYSTEMU] Wystąpił nieoczekiwany problem: {e}")

if __name__ == "__main__":
    if API_KEY == 'TWÓJ_KLUCZ_API' or not API_KEY:
        print("⚠️ Zanim uruchomisz, wklej swoje klucze API w kodzie skryptu!")
    else:
        test_api()