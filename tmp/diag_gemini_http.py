import requests
import os
from dotenv import load_dotenv
load_dotenv()

key = "AIzaSyD6X6w80bwoP7wcJ6T9Enlw4pdLwdOiA9Y"
results = []

for v in ["v1", "v1beta"]:
    for m in ["gemini-1.5-flash", "gemini-1.0-pro", "gemini-pro"]:
        url = f"https://generativelanguage.googleapis.com/{v}/models/{m}:generateContent?key={key}"
        try:
            resp = requests.post(url, json={"contents": [{"parts": [{"text": "hi"}]}]}, timeout=10)
            status = "SUCCESS" if resp.status_code == 200 else f"FAILED ({resp.status_code})"
            results.append(f"{v}/{m}: {status} - {resp.text[:50]}")
        except Exception as e:
            results.append(f"{v}/{m}: ERROR - {e}")

for r in results:
    print(r)
