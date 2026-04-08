import requests

TOKEN = "8423220609:AAE6yrPVGS7Fv2vIgkbiKWhTINMRlA_F__s"
CHAT_ID = "8639573942"

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
payload = {
    "chat_id": CHAT_ID,
    "text": "🚀 <b>TEST SYSTEMU FRONTLINE</b>\nZarządzanie powiadomieniami działa!",
    "parse_mode": "HTML"
}

print("Wysyłam zapytanie do serwerów Telegrama...")
response = requests.post(url, data=payload)

print(f"Status połączenia: {response.status_code}")
print(f"Odpowiedź serwera: {response.text}")