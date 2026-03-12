import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv('.env')
keys = os.environ.get('GEMINI_API_KEYS', '').split(',')
api_key = keys[0] if keys else os.environ.get('GEMINI_API_KEY')
genai.configure(api_key=api_key)

with open('models.txt', 'w', encoding='utf-8') as f:
    for m in genai.list_models():
        f.write(f"{m.name} - {m.supported_generation_methods}\n")
