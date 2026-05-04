
import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
model_name = "llama-3.3-70b-versatile"

if not api_key:
    print("Error: GROQ_API_KEY not found in .env")
else:
    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": "Say hello in 5 words."}],
        )
        print(f"Success with {model_name}: {response.choices[0].message.content}")
    except Exception as e:
        print(f"Error with {model_name}: {e}")
