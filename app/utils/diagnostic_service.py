import os
import google.generativeai as genai
import requests
from datetime import datetime, timedelta
from app.models import APIKeyTracker
from app import db

def validate_one_key(tracker):
    """Performs a real-world validation test for a single API key tracker."""
    now = datetime.now()
    try:
        if tracker.provider == 'gemini':
            genai.configure(api_key=tracker.api_key)
            # Use specific model name that is widely supported
            model = genai.GenerativeModel('gemini-1.5-flash-latest')
            model.generate_content("ping", generation_config={"max_output_tokens": 5})
            
            tracker.status = 'active'
            tracker.error_message = None
            tracker.last_used = now
            return True
            
        elif tracker.provider == 'groq':
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {tracker.api_key}",
                "Content-Type": "application/json"
            }
            data = {
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5
            }
            resp = requests.post(url, headers=headers, json=data, timeout=10)
            if resp.status_code == 200:
                tracker.status = 'active'
                tracker.error_message = None
                tracker.last_used = now
                return True
            else:
                tracker.status = 'error'
                tracker.error_message = f"HTTP {resp.status_code}: {resp.text[:100]}"
                return False
                
        elif tracker.provider == 'ollama':
            # Ollama "key" is actually the Base URL
            resp = requests.get(tracker.api_key, timeout=5)
            if resp.status_code == 200:
                tracker.status = 'active'
                tracker.error_message = None
                tracker.last_used = now
                return True
            else:
                tracker.status = 'error'
                tracker.error_message = f"Local Ollama unreachable: {resp.status_code}"
                return False
                
    except Exception as e:
        tracker.status = 'error'
        tracker.error_message = str(e)[:200]
        return False

def proactive_self_heal():
    """Iterates through all keys and performs a full diagnostic audit."""
    print(f"[{datetime.now()}] Starting Proactive Self-Healing Audit...")
    trackers = APIKeyTracker.query.all()
    count_fixed = 0
    count_broken = 0
    
    for t in trackers:
        # We only re-verify keys that are NOT currently active
        # OR keys that have been active but haven't been checked in 10 minutes
        needs_check = (t.status != 'active')
        if t.status == 'active' and t.last_used:
            if datetime.now() - t.last_used > timedelta(minutes=10):
                needs_check = True
        
        if needs_check:
            success = validate_one_key(t)
            if success: count_fixed += 1
            else: count_broken += 1
            
    try:
        db.session.commit()
        print(f"Audit Complete. Fixed: {count_fixed}, Broken: {count_broken}")
    except Exception as e:
        db.session.rollback()
        print(f"Audit Commit Failed: {e}")
