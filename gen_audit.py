import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

results = []
keys = os.environ.get('GEMINI_API_KEYS', '').split(',')
for k in keys:
    k = k.strip()
    if not k: continue
    
    status = {"key": f"{k[:8]}...", "flash": "Testing...", "pro": "Testing..."}
    
    # Test Flash
    try:
        genai.configure(api_key=k)
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content("hi")
        status["flash"] = "SUCCESS"
    except Exception as e:
        status["flash"] = str(e)[:200]
        
    # Test Pro
    try:
        model = genai.GenerativeModel('gemini-1.5-pro')
        response = model.generate_content("hi")
        status["pro"] = "SUCCESS"
    except Exception as e:
        status["pro"] = str(e)[:200]
        
    results.append(status)

with open("api_audit_report.txt", "w", encoding="utf-8") as f:
    f.write("--- Gemini API Audit Report ---\n")
    for r in results:
        f.write(f"Key {r['key']}:\n")
        f.write(f"  Flash: {r['flash']}\n")
        f.write(f"  Pro:   {r['pro']}\n")
        f.write("-" * 20 + "\n")

import requests
print("\n--- Testing Groq ---")
groq_keys = os.environ.get('GROQ_API_KEYS', '').split(',')
with open("api_audit_report.txt", "a", encoding="utf-8") as f:
    f.write("\n--- Groq API Audit Report ---\n")
    for k in groq_keys:
        k = k.strip()
        if not k: continue
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
            data = {"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 5}
            resp = requests.post(url, headers=headers, json=data, timeout=10)
            if resp.status_code == 200:
                res = "SUCCESS"
            else:
                res = f"FAILED: {resp.status_code} - {resp.text[:100]}"
            f.write(f"Key {k[:8]}... : {res}\n")
        except Exception as e:
            f.write(f"Key {k[:8]}... : ERROR {str(e)}\n")
