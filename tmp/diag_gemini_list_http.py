import requests
import os
from dotenv import load_dotenv
load_dotenv()

key = "AIzaSyD6X6w80bwoP7wcJ6T9Enlw4pdLwdOiA9Y"
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"

print(f"Listing models for key via HTTP...")
try:
    resp = requests.get(url, timeout=10)
    if resp.status_code == 200:
        data = resp.json()
        for m in data.get('models', []):
            print(f"Name: {m['name']}, Methods: {m.get('supportedGenerationMethods', [])}")
    else:
        print(f"FAILED: {resp.status_code} {resp.text[:200]}")
except Exception as e:
    print(f"ERROR: {e}")
