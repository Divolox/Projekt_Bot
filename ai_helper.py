import google.generativeai as genai
import os
import time

# --- KONFIGURACJA ---
# Wklej tu swój klucz (ten sam, na którym zadziałał skrypt sprawdzający)
API_KEY = "TUTAJ_JEST_KLUCZ_API" 

if os.getenv("GEMINI_API_KEY"):
    API_KEY = os.getenv("GEMINI_API_KEY")

try:
    genai.configure(api_key=API_KEY)
except Exception as e:
    print(f"❌ Błąd konfiguracji klucza: {e}")

# ZWYCIĘZCA POLOWANIA:
MODEL_NAME = "models/gemini-flash-latest"

def ask_ai(prompt, retries=3):
    system_instruction = (
        "Jesteś ekspertem tradingowym. "
        "Analizuj dane techniczne i sentyment. "
        "Odpowiadaj krótko i wyłącznie w formacie JSON."
    )
    
    generation_config = {
        "temperature": 0.5,
        "max_output_tokens": 4000,
    }

    try:
        model = genai.GenerativeModel(
            model_name=MODEL_NAME,
            system_instruction=system_instruction
        )
        
        for attempt in range(retries):
            try:
                # print(f"   🤖 [DEBUG] Pytam model: {MODEL_NAME}...")
                response = model.generate_content(
                    prompt,
                    generation_config=generation_config
                )
                
                if response.text:
                    return response.text
                else:
                    print(f"   ⚠️ [DEBUG] Pusta odpowiedź od Google (Próba {attempt+1})")
            
            except Exception as e:
                error_msg = str(e)
                # Obsługa błędów limitów
                if "429" in error_msg or "Quota" in error_msg:
                    print(f"⏳ Limit Google (429/Quota). Czekam 60s...")
                    time.sleep(60)
                elif "500" in error_msg or "503" in error_msg:
                    print(f"⚠️ Błąd serwera Google. Czekam 5s...")
                    time.sleep(5)
                else:
                    print(f"⚠️ Błąd AI: {e}")
                    time.sleep(2)
        
    except Exception as e:
        print(f"❌ Błąd inicjalizacji modelu: {e}")

    return None