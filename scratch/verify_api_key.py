
import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
print(f"Loaded API Key: {api_key[:10]}...{api_key[-5:] if api_key else 'NONE'}")

if not api_key:
    print("Error: GEMINI_API_KEY not found in environment.")
else:
    try:
        genai.configure(api_key=api_key)
        # Try to list models (requires valid key)
        models = genai.list_models()
        print("Successfully connected to Gemini API!")
        print("Available models:")
        for m in models:
            if 'generateContent' in m.supported_generation_methods:
                print(f" - {m.name}")
    except Exception as e:
        print(f"Error connecting to Gemini API: {e}")
