import requests
import os
from dotenv import load_dotenv
load_dotenv()

key = "AIzaSyD6X6w80bwoP7wcJ6T9Enlw4pdLwdOiA9Y"
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"

try:
    resp = requests.get(url, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        models = [m['name'] for m in data.get('models', [])]
        print("EXACT_MODELS_START")
        for m in models:
            print(m)
        print("EXACT_MODELS_END")
except Exception as e:
    print(f"ERROR: {e}")
