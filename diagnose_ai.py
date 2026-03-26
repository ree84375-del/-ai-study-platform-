import os
import requests
import google.generativeai as genai
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def test_gemini(key):
    try:
        genai.configure(api_key=key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content("Hi", request_options={"timeout": 10.0})
        return "SUCCESS", response.text[:20]
    except Exception as e:
        err = str(e)
        if "429" in err: return "429 QUOTA EXCEEDED", err
        if "400" in err or "401" in err: return "401 INVALID KEY", err
        return "ERROR", err

def test_groq(key):
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        data = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 5}
        resp = requests.post(url, json=data, headers=headers, timeout=10)
        if resp.status_code == 200: return "SUCCESS", resp.json()['choices'][0]['message']['content']
        if resp.status_code == 401: return "401 INVALID KEY", resp.text
        if resp.status_code == 429: return "429 QUOTA EXCEEDED", resp.text
        return f"ERROR {resp.status_code}", resp.text
    except Exception as e:
        return "ERROR", str(e)

def test_voyage(key):
    try:
        url = "https://api.voyageai.com/v1/embeddings"
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        data = {"input": ["Hi"], "model": "voyage-3"}
        resp = requests.post(url, json=data, headers=headers, timeout=10)
        if resp.status_code == 200: return "SUCCESS", "Embedded successfully"
        if resp.status_code == 401: return "401 INVALID KEY", resp.text
        return f"ERROR {resp.status_code}", resp.text
    except Exception as e:
        return "ERROR", str(e)

def run_diagnostics():
    print(f"--- AI API Diagnostics ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) ---")
    
    # Gemini
    gemini_keys = os.environ.get('GEMINI_API_KEYS', os.environ.get('GEMINI_API_KEY', '')).split(',')
    print(f"\n[Gemini] Found {len(gemini_keys)} keys")
    for i, k in enumerate(gemini_keys):
        k = k.strip()
        if not k: continue
        status, detail = test_gemini(k)
        print(f"  Key {i+1} ({k[:6]}...{k[-4:]}): {status}")
        if status != "SUCCESS": print(f"    Detail: {detail}")

    # Groq
    groq_keys = os.environ.get('GROQ_API_KEYS', os.environ.get('GROQ_API_KEY', '')).split(',')
    print(f"\n[Groq] Found {len(groq_keys)} keys")
    for i, k in enumerate(groq_keys):
        k = k.strip()
        if not k: continue
        status, detail = test_groq(k)
        print(f"  Key {i+1} ({k[:6]}...{k[-4:]}): {status}")
        if status != "SUCCESS": print(f"    Detail: {detail}")

    # Voyage
    voyage_key = os.environ.get('VOYAGE_API_KEY', '').strip()
    if voyage_key:
        print(f"\n[Voyage] Testing Key ({voyage_key[:6]}...)")
        status, detail = test_voyage(voyage_key)
        print(f"  Status: {status}")
        if status != "SUCCESS": print(f"    Detail: {detail}")
    else:
        print("\n[Voyage] No key found in environment variables.")

    print("\n--- End of Diagnostics ---")

if __name__ == "__main__":
    run_diagnostics()
