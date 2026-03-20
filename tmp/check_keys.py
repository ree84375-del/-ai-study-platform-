import os
import requests
from dotenv import load_dotenv

load_dotenv()
groq_keys = os.environ.get('GROQ_API_KEYS', '').split(',')
valid_groq = []
for k in groq_keys:
    if not k.strip(): continue
    resp = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {k.strip()}"}, json={"model": "llama-3.1-8b-instant", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5})
    if resp.status_code == 200:
        valid_groq.append(k)

print(f"Valid Groq: {valid_groq}")
