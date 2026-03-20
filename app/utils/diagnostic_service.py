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
            
            # Dynamic Discovery: List models available for this specific key
            try:
                available_models = []
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        available_models.append(m.name)
                
                if not available_models:
                    tracker.status = 'error'
                    tracker.error_message = "No models available for this key."
                    tracker.cooldown_until = now + timedelta(days=1)
                    return False
                
                # Try the discovered models
                last_err = None
                # Prioritize flash for speed, then others
                priority_order = ['gemini-1.5-flash', 'gemini-1.5-flash-8b', 'gemini-1.0-pro', 'gemini-pro']
                
                # Re-sort available_models to put priority ones first
                test_list = []
                for p in priority_order:
                    full_p = f"models/{p}" if not p.startswith("models/") else p
                    if full_p in available_models:
                        test_list.append(full_p)
                
                # Add the rest
                for m_name in available_models:
                    if m_name not in test_list:
                        test_list.append(m_name)
                
                for m_name in test_list:
                    try:
                        model = genai.GenerativeModel(m_name)
                        model.generate_content("ping", generation_config={"max_output_tokens": 5})
                        
                        tracker.status = 'standby'
                        tracker.error_message = None
                        tracker.last_used = now
                        tracker.cooldown_until = None
                        return True
                    except Exception as e:
                        last_err = str(e)
                        continue
                
                tracker.status = 'error'
                tracker.error_message = f"All discovered models failed. Last error: {last_err[:150]}"
                tracker.cooldown_until = now + timedelta(minutes=10)
                return False
                
            except Exception as e:
                tracker.status = 'error'
                tracker.error_message = f"Discovery failed: {str(e)[:150]}"
                tracker.cooldown_until = now + timedelta(minutes=5)
                return False
            
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
            try:
                resp = requests.post(url, headers=headers, json=data, timeout=10)
                if resp.status_code == 200:
                    tracker.status = 'standby'
                    tracker.error_message = None
                    tracker.last_used = now
                    tracker.cooldown_until = None
                    return True
                else:
                    tracker.status = 'error'
                    err_msg = f"HTTP {resp.status_code}: {resp.text[:100]}"
                    tracker.error_message = err_msg
                    
                    # Permanent Block: Restricted organization
                    if "restricted" in resp.text.lower() or resp.status_code == 403:
                        tracker.cooldown_until = now + timedelta(days=7) # Wait 7 days for restricted
                    else:
                        tracker.cooldown_until = now + timedelta(minutes=5)
                    return False
            except Exception as e:
                tracker.status = 'error'
                tracker.error_message = f"Connection error: {str(e)[:100]}"
                tracker.cooldown_until = now + timedelta(minutes=2)
                return False
                
        elif tracker.provider == 'ollama':
            # Ollama "key" is actually the Base URL
            base_url = tracker.api_key.strip() if tracker.api_key else ""
            if not base_url.startswith("http"):
                tracker.status = 'error'
                tracker.error_message = "Invalid URL format (Must start with http:// or https://)"
                tracker.cooldown_until = now + timedelta(days=365) # Permanent error for junk strings
                return False
                
            try:
                resp = requests.get(base_url, timeout=5)
                if resp.status_code == 200:
                    tracker.status = 'standby'
                    tracker.error_message = None
                    tracker.last_used = now
                    tracker.cooldown_until = None
                    return True
                else:
                    tracker.status = 'error'
                    tracker.error_message = f"Local Ollama unreachable: {resp.status_code}"
                    tracker.cooldown_until = now + timedelta(minutes=5)
                    return False
            except Exception as e:
                tracker.status = 'error'
                tracker.error_message = f"Ollama Connect Error: {str(e)[:100]}"
                tracker.cooldown_until = now + timedelta(minutes=5)
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
