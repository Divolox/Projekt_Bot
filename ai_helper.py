import google.generativeai as genai
import os
import time
import json
import re

# --- KONFIGURACJA ---
API_KEY = "." 

if os.getenv("GEMINI_API_KEY"):
    API_KEY = os.getenv("GEMINI_API_KEY")

try:
    genai.configure(api_key=API_KEY)
except Exception as e:
    print(f"❌ Błąd konfiguracji klucza: {e}")

MODEL_NAME = "models/gemini-flash-latest"

def clean_and_parse_json(text):
    """
    To jest ta funkcja 'konwertująca'.
    Bierze brudny tekst od AI i robi z niego zrozumiałą dla Pythona Listę/Słownik.
    """
    try:
        # 1. Usuwamy znaczniki Markdown (```json ... ```)
        text = text.replace("```json", "").replace("```", "").strip()
        
        # 2. Próbujemy znaleźć JSON w tekście (jeśli AI dodało jakiś wstęp)
        match = re.search(r'(\{.*\}|\[.*\])', text, re.DOTALL)
        if match:
            text = match.group(0)
            
        # 3. Konwersja tekstu na obiekt Python (Lista lub Słownik)
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"⚠️ Błąd: AI zwróciło tekst, którego nie da się zamienić na kod: {text[:50]}...")
        return None

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
                response = model.generate_content(
                    prompt,
                    generation_config=generation_config
                )
                
                if response.text:
                    # TUTAJ ROBIMY KONWERSJĘ
                    # Zwracamy gotowy obiekt (Listę/Słownik), a nie tekst!
                    return clean_and_parse_json(response.text)
                else:
                    print(f"   ⚠️ [DEBUG] Pusta odpowiedź od Google (Próba {attempt+1})")
            
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg or "Quota" in error_msg:
                    print(f"⏳ Limit Google (429/Quota). Czekam 60s...")
                    time.sleep(60)
                elif "500" in error_msg or "503" in error_msg:
                    time.sleep(5)
                else:
                    print(f"⚠️ Błąd AI: {e}")
                    time.sleep(2)
        
    except Exception as e:
        print(f"❌ Błąd inicjalizacji modelu: {e}")

    return None