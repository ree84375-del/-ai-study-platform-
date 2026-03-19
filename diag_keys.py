import os
import requests
import json
from dotenv import load_dotenv

load_dotenv()

def test_gemini(key):
    # Use the standard v1 models path
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={key}"
    headers = {'Content-Type': 'application/json'}
    data = {"contents": [{"parts":[{"text": "hi"}]}]}
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        return resp.status_code, resp.text
    except Exception as e:
        return 500, str(e)

def test_groq(key):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    data = {"model": "llama3-8b-8192", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}
    try:
        resp = requests.post(url, headers=headers, json=data, timeout=10)
        return resp.status_code, resp.text
    except Exception as e:
        return 500, str(e)

print("--- Gemini Keys Test ---")
gemini_keys = os.environ.get('GEMINI_API_KEYS', '').split(',')
for k in gemini_keys:
    k = k.strip()
    if not k: continue
    code, text = test_gemini(k)
    print(f"Key {k[:8]}... : Code {code}")
    if code != 200:
        print(f"  Error: {text[:200]}")

print("\n--- Groq Keys Test ---")
groq_keys = os.environ.get('GROQ_API_KEYS', '').split(',')
for k in groq_keys:
    k = k.strip()
    if not k: continue
    code, text = test_groq(k)
    print(f"Key {k[:8]}... : Code {code}")
    if code != 200:
        print(f"  Error: {text[:200]}")
