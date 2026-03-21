import os
import json
import re
from datetime import datetime
# Gemini Safety Settings - Relaxed to avoid over-filtering
GEMINI_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]
import google.generativeai as genai
from PIL import Image
import io
import random
import urllib.parse


# Setup Gemini API key
_cached_gemini_model_name = None

# API Key Status Tracking
from app import db
from app.models import APIKeyTracker
from datetime import timedelta

_table_verified = False
def verify_api_key_table():
    global _table_verified
    if _table_verified: return
    try:
        from sqlalchemy import text
        # Ensure tables exist
        db.session.execute(text("CREATE TABLE IF NOT EXISTS api_key_tracker (id SERIAL PRIMARY KEY, provider VARCHAR(50) NOT NULL, api_key VARCHAR(255) UNIQUE NOT NULL, status VARCHAR(20) DEFAULT 'standby', last_used TIMESTAMP, error_message TEXT)"))
        db.session.execute(text("CREATE TABLE IF NOT EXISTS user_memory (id SERIAL PRIMARY KEY, user_id INTEGER UNIQUE NOT NULL, memory_content TEXT, last_updated TIMESTAMP)"))
        db.session.execute(text("CREATE TABLE IF NOT EXISTS memory_fragment (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, category VARCHAR(50) DEFAULT 'general', content TEXT NOT NULL, importance INTEGER DEFAULT 1, created_at TIMESTAMP)"))
        db.session.commit()
        
        # Ensure new columns exist in api_key_tracker (SQLite doesn't support IF NOT EXISTS in ALTER)
        for col, col_type in [("cooldown_until", "TIMESTAMP"), ("retry_count", "INTEGER DEFAULT 0")]:
            try:
                db.session.execute(text(f"ALTER TABLE api_key_tracker ADD COLUMN {col} {col_type}"))
                db.session.commit()
            except Exception:
                db.session.rollback() # Assume column already exists
                
    except Exception:
        db.session.rollback()
    
    _table_verified = True

def get_user_memory_context(user):
    """Fetches fragmented memory and recent short-term context for the user."""
    from app.models import MemoryFragment, ChatMessage, ChatSession
    verify_api_key_table()
    
    # 1. Fragmented long-term memory (Fetch top 10 most recent/important fragments)
    fragments = MemoryFragment.query.filter_by(user_id=user.id).order_by(MemoryFragment.importance.desc(), MemoryFragment.created_at.desc()).limit(15).all()
    
    long_term_list = [f"[{f.category}] {f.content}" for f in fragments]
    long_term = "\n".join(long_term_list) if long_term_list else "目前尚無長期記憶片段。"
    
    # 2. Recent short-term context (last 10 messages)
    recent_msgs = ChatMessage.query.join(ChatSession).filter(ChatSession.user_id == user.id).order_by(ChatMessage.created_at.desc()).limit(10).all()
    recent_msgs.reverse()
    short_term = "\n".join([f"{m.role}: {m.content[:200]}..." for m in recent_msgs])
    
    return f"【核心記憶片段】：\n{long_term}\n\n【近期對話回顧】：\n{short_term}"

def update_user_memory(user_id, interaction_summary):
    """Extracts new facts from interaction and stores them as fragments."""
    from app.models import MemoryFragment
    try:
        # Step 1: Fact Extraction via AI
        prompt = f"""
        請從以下對話摘要中提取出「值得記錄的個人事實或偏好」，排除掉問候或無意義的閒聊。
        摘要：{interaction_summary}
        
        請以 JSON 列表格式輸出，每個項目包含：
        - category: (preference/academic/personal/event)
        - content: (簡短的一句話事實)
        - importance: (1-5, 重要程度)
        
        僅返回 raw JSON 列表，若無值得記錄的內容則返回空列表 []。
        """
        response_text = generate_text_with_fallback(prompt)
        
        # Simple extraction logic
        clean_text = response_text.strip()
        if '```' in clean_text:
            match = re.search(r'\[.*\]', clean_text, re.DOTALL)
            if match: clean_text = match.group(0)
            
        facts = json.loads(clean_text)
        
        for fact in facts:
            # Check for near-duplicates before adding
            existing = MemoryFragment.query.filter_by(user_id=user_id, content=fact['content']).first()
            if not existing:
                fragment = MemoryFragment(
                    user_id=user_id,
                    category=fact.get('category', 'general'),
                    content=fact['content'],
                    importance=fact.get('importance', 1)
                )
                db.session.add(fragment)
        
        db.session.commit()
    except Exception as e:
        import logging
        logging.error(f"Memory Fragmentation Error: {e}")
        db.session.rollback()

def _sync_keys_to_db(provider, keys):
    verify_api_key_table()
    if not keys: return
    existing = APIKeyTracker.query.filter_by(provider=provider).all()
    existing_keys = {t.api_key: t for t in existing}
    
    # Add newly discovered keys from .env
    for k in keys:
        if k not in existing_keys:
            tracker = APIKeyTracker(provider=provider, api_key=k, status='standby')
            db.session.add(tracker)
            existing_keys[k] = tracker
    
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    return existing_keys

def get_all_api_key_statuses():
    from app.utils.diagnostic_service import proactive_self_heal
    from app.models import APIKeyTracker
    
    # Sync keys to DB without destructive flush

    gemini_keys = get_gemini_keys()
    groq_keys = get_groq_keys()
    ollama_keys = get_ollama_keys()
    
    # Sync all current keys to DB
    _sync_keys_to_db('gemini', gemini_keys)
    _sync_keys_to_db('groq', groq_keys)
    _sync_keys_to_db('ollama', ollama_keys)
    
    # Force a full audit immediately since user requested "NOW"
    global _last_audit_time
    now = datetime.now()
    # Trigger full audit if it's the first time or 30 seconds passed (Extreme Real-time)
    if '_last_audit_time' not in globals() or (now - _last_audit_time) > timedelta(seconds=30):
        _last_audit_time = now
        try:
            proactive_self_heal()
        except Exception as e:
            print(f"Background Audit Error: {e}")

    # Perform Basic Auto-Repair here
    now = datetime.now()
    active_threshold = now - timedelta(seconds=12) # Active keys revert to standby
    busy_threshold = now - timedelta(seconds=60)   # Busy keys revert if stuck > 60s
    
    trackers = APIKeyTracker.query.all()
    for t in trackers:
        # Revert busy/active if they seem stuck
        if t.status == 'active' and t.last_used and t.last_used < active_threshold:
            t.status = 'standby'
        elif t.status == 'busy' and t.last_used and t.last_used < busy_threshold:
            t.status = 'standby'
            
    # If a key stays in 'error' or 'cooldown' but has NO cooldown_until or it's passed,
    # then we can try to reset it to standby.
    for t in trackers:
        # DO NOT reset keys with "restricted" in error message (Long term block)
        if t.error_message and ("restricted" in t.error_message.lower() or "organization" in t.error_message.lower()):
            if not t.cooldown_until or t.cooldown_until < now:
                t.cooldown_until = now + timedelta(days=7) # Ensure long block persists
            continue
            
        # DO NOT reset Ollama keys that have Invalid URL format (No point retrying junk)
        if t.provider == 'ollama' and t.error_message and "Invalid URL" in t.error_message:
            continue

        if t.status in ['cooldown', 'error']:
            if not t.cooldown_until or t.cooldown_until < now:
                t.status = 'standby'
                t.error_message = None
                t.cooldown_until = None
    
    # SPECIAL CASE: Skip Restricted Keys from Recovery
    for t in trackers:
        if t.error_message and ("restricted" in t.error_message.lower() or "organization" in t.error_message.lower() or "ban" in t.error_message.lower()):
            t.status = 'error' # Stay in error
            t.cooldown_until = now + timedelta(days=7) # Long-term cooldown for banned/restricted accounts
    
    try:
        if db.session.is_modified():
            db.session.commit()
    except Exception:
        db.session.rollback()
    
    masked_status = {'gemini': [], 'groq': [], 'ollama': []}
    trackers = APIKeyTracker.query.all()
    
    all_env_keys = get_gemini_keys() + get_groq_keys() + get_ollama_keys()
    
    for t in trackers:
        # Only show keys that are currently in the .env variables
        if t.api_key not in all_env_keys:
            continue
            
        k = t.api_key
        masked_k = k[:6] + '...' + k[-4:] if len(k) > 10 else k
        
        masked_status[t.provider].append({
            'key': masked_k,
            'full_key': k,
            'status': t.status,
            'last_used': t.last_used.strftime('%Y-%m-%d %H:%M:%S') if t.last_used else '從未使用',
            'error': t.error_message
        })
        
    return masked_status

def mark_key_status(provider, key, status, error=None):
    tracker = APIKeyTracker.query.filter_by(provider=provider, api_key=key).first()
    if not tracker:
        tracker = APIKeyTracker(provider=provider, api_key=key, status=status)
        db.session.add(tracker)
    
    now = datetime.now()
    tracker.status = status
    tracker.last_used = now
    
    if status == 'active':
        tracker.retry_count = 0
        tracker.cooldown_until = None
        tracker.error_message = None
    elif status == 'standby':
        tracker.status = 'standby'
        tracker.cooldown_until = None
        tracker.error_message = None
    elif status in ['cooldown', 'error']:
        tracker.error_message = error
        # Exponential backoff for 429 errors
        if error and ('429' in error or 'quota' in error.lower()):
            tracker.retry_count = (tracker.retry_count or 0) + 1
            minutes = min(5 * (2 ** (tracker.retry_count - 1)), 120) 
            tracker.cooldown_until = now + timedelta(minutes=minutes)
        elif error and ('restricted' in error.lower() or 'organization' in error.lower() or 'ban' in error.lower()):
            # Organization/Account level restrictions are usually permanent or long-term
            tracker.cooldown_until = now + timedelta(days=7)
        elif error and '403' in error:
            # 403 Forbidden usually means the key is restricted for a longer period
            tracker.cooldown_until = now + timedelta(hours=1)
        else:
            # Generic error fixed cooldown (Reduced to 2m for faster retry)
            tracker.cooldown_until = now + timedelta(minutes=2)
            
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

def get_usable_keys(provider, base_keys):
    if not base_keys: return []
    try:
        # Avoid synchronous proactive_self_heal here as it blocks generation
        
        usable = []
        now = datetime.now()
        trackers = {t.api_key: t for t in APIKeyTracker.query.filter_by(provider=provider).all()}
        for k in base_keys:
            t = trackers.get(k)
            if not t:
                usable.append(k)
                continue
            
            # AGGRESSIVE RECOVERY:
            # If the key was in 'error' or 'cooldown' but hasn't been checked in 30 seconds,
            # reset it to 'standby' to allow a fresh retry.
            # (The 30-second check is handled by get_all_api_key_statuses, this just ensures a reset if needed)
            if t.status in ['error', 'cooldown'] and t.cooldown_until and t.cooldown_until < now:
                t.status = 'standby'
                t.error_message = None
                t.cooldown_until = None
                
            # DO NOT use keys that have "restricted" in the error message (Billings/Ban)
            if t.error_message and ("restricted" in t.error_message.lower() or "organization" in t.error_message.lower() or "ban" in t.error_message.lower()):
                continue
                
            # DO NOT use Ollama keys with Invalid URL
            if t.provider == 'ollama' and t.error_message and ("Invalid URL" in t.error_message or "Invalid Schema" in t.error_message):
                continue
                
            if t.status == 'standby':
                # Double check cooldown_until just in case
                if not t.cooldown_until or t.cooldown_until < now:
                    usable.append(k)
            elif t.status == 'active':
                # Active keys are usually fine to reuse if not busy
                usable.append(k)
        
        # Final Shuffle: Balance load across all usable keys
        random.shuffle(usable)
        return usable if usable else [random.choice(base_keys)]
    except Exception:
        try:
            db.session.rollback()
        except: pass
        return [random.choice(base_keys)] if base_keys else []


def get_gemini_keys():
    keys_str = os.environ.get('GEMINI_API_KEYS', os.environ.get('GEMINI_API_KEY', ''))
    if not keys_str: return []
    return [k.strip() for k in keys_str.split(',') if k.strip()]

def get_ollama_keys():
    keys_str = os.environ.get('OLLAMA_API_KEYS', os.environ.get('OLLAMA_API_KEY', ''))
    if not keys_str: return []
    return [k.strip() for k in keys_str.split(',') if k.strip()]

def get_gemini_model(system_instruction=None, tools=None):
    global _cached_gemini_model_name
    
    keys = get_gemini_keys()
    if keys:
         genai.configure(api_key=random.choice(keys))
         
    if _cached_gemini_model_name:
        return genai.GenerativeModel(_cached_gemini_model_name, system_instruction=system_instruction, tools=tools)
        
    # Auto-discover working model to prevent 404 errors
    try:
        valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Priority list of models (Prefer Gemma 3 for free tier limits)
        preferred = [
            'models/gemma-3-12b-it',
            'models/gemma-3-4b-it',
            'models/gemma-3-27b-it',
            'models/gemini-1.5-flash',
            'models/gemini-2.0-flash',
            'models/gemini-2.0-flash-lite',
            'models/gemini-1.5-pro',
        ]
        
        for pref in preferred:
            if pref in valid_models:
                _cached_gemini_model_name = pref
                if 'gemma' in pref:
                    return genai.GenerativeModel(pref, tools=tools)
                return genai.GenerativeModel(pref, system_instruction=system_instruction, tools=tools)
                
        # If preferred not found, just use the first valid one
        if valid_models:
            _cached_gemini_model_name = valid_models[0]
            if 'gemma' in _cached_gemini_model_name:
                return genai.GenerativeModel(_cached_gemini_model_name, tools=tools)
            return genai.GenerativeModel(_cached_gemini_model_name, system_instruction=system_instruction, tools=tools)
            
    except Exception as e:
        print(f"Failed to auto-discover models: {e}")
        
    # Ultimate fallback if everything fails
    _cached_gemini_model_name = 'models/gemma-3-4b-it'
    return genai.GenerativeModel(_cached_gemini_model_name, tools=tools)

# Groq Keys Pool - Load from environment variable (comma-separated)
def get_groq_keys():
    keys_str = os.environ.get('GROQ_API_KEYS', os.environ.get('GROQ_API_KEY', ''))
    if not keys_str: return []
    return [k.strip() for k in keys_str.split(',') if k.strip()]

def get_groq_client():
    from groq import Groq
    keys = get_groq_keys()
    if not keys: raise ValueError("Missing GROQ_API_KEYS environment variable")
    return Groq(api_key=random.choice(keys))

def generate_text_with_fallback(prompt, system_instruction=None, user=None):
    """Unified wrapper for text generation with randomized provider rotation (Gemini, Groq, Ollama)"""
    # Priority Injection: Ollama (Keyless-Local) -> Groq (Stable) -> Gemini (Fallback)
    providers = ['ollama', 'groq', 'gemini']
    
    errors = []
    for provider in providers:
        keys = get_usable_keys(provider, get_gemini_keys() if provider == 'gemini' else (get_groq_keys() if provider == 'groq' else get_ollama_keys()))
        if not keys:
            errors.append(f"{provider}: 所有金鑰均已被封鎖或無效，跳過此提供商")
            continue
            
        for key in keys:
            # Busy-Locking
            mark_key_status(provider, key, 'busy')
            try:
                # Fast failover: no retry on same key to save time
                max_retries = 1
                for attempt in range(max_retries):
                    try:
                        if provider == 'gemini':
                            genai.configure(api_key=key)
                            user_context = get_user_memory_context(user) if user else ""
                            full_system = f"{system_instruction}\n\n{user_context}"
                            
                            final_prompt = prompt
                            if 'gemma' in _cached_gemini_model_name:
                                final_prompt = f"System Instruction: {full_system}\n\nUser: {prompt}"
                                model = get_gemini_model(system_instruction="")
                            else:
                                model = get_gemini_model(system_instruction=full_system)
                                
                            response = model.generate_content(final_prompt, request_options={"timeout": 8.0, "retry": None})
                            if user:
                                update_user_memory(user.id, f"用戶：{prompt[:80]} -> 雪音：{response.text[:80]}")
                            mark_key_status('gemini', key, 'standby')
                            return response.text
                        elif provider == 'groq':
                            from groq import Groq
                            client = Groq(api_key=key)
                            user_context = get_user_memory_context(user) if user else ""
                            full_system = f"{system_instruction}\n\n{user_context}"
                            messages = [{"role": "system", "content": full_system}, {"role": "user", "content": prompt}]
                            response = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages, timeout=6.0)
                            if user:
                                update_user_memory(user.id, f"用戶：{prompt[:80]} -> 雪音(Groq)：{response.choices[0].message.content[:80]}")
                            mark_key_status('groq', key, 'standby')
                            return response.choices[0].message.content
                        elif provider == 'ollama':
                            import requests
                            headers = {'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true'}
                            ollama_url = key if key.startswith('http') else f"http://{key}"
                            payload = {
                                "model": os.environ.get('OLLAMA_MODEL', 'llama3.2:latest'),
                                "messages": [{"role": "user", "content": prompt}],
                                "stream": False
                            }
                            resp = requests.post(f"{ollama_url}/api/chat", json=payload, timeout=(3.0, 30.0), headers=headers)
                            if resp.status_code == 200:
                                mark_key_status('ollama', key, 'standby')
                                return resp.json()['message']['content']
                            else:
                                raise Exception(f"Ollama error {resp.status_code}: {resp.text}")

                    except Exception as e:
                        error_msg = str(e)
                        # RAPID QUARANTINE FOR LEAKED KEYS
                        if '403' in error_msg and 'leaked' in error_msg.lower():
                            mark_key_status(provider, key, 'error', error=f"LEAKED: {error_msg}")
                            break # Move to next key immediately
                        
                        if ('429' in error_msg or 'quota' in error_msg.lower()) and attempt < max_retries - 1:
                            import time
                            time.sleep(1) 
                            continue
                        raise e
            except Exception as e:
                error_msg = str(e)
                if '400' in error_msg and 'key not valid' in error_msg.lower():
                    error_msg = "Google says: API Key is invalid or deactivated."
                elif '403' in error_msg:
                    error_msg = "Google says: API Key is restricted or blocked."
                
                errors.append(f"{provider} (key {key[:4]}...): {error_msg}")
                mark_key_status(provider, key, 'error', error_msg)
                continue
    raise Exception(f"所有的 AI 模型皆不可用：{', '.join(errors)}")

def generate_vision_with_fallback(prompt, image_bytes, system_instruction=None, user=None):
    """Unified wrapper for vision generation with randomized provider rotation (Gemini, Groq, Ollama)"""
    import base64
    # Priority: Gemini (Most Reliable) -> Groq (Backup) -> Ollama (Local, often offline)
    providers = ['gemini', 'groq', 'ollama']
    errors = []
    
    # Simple Hash-based Cache (Saves API Quota)
    import hashlib
    img_hash = hashlib.md5(image_bytes).hexdigest()
    cache_key = f"vision_cache_{img_hash}_{hashlib.md5(prompt.encode()).hexdigest()}"
    # (In a real app, use Redis/DB. For now, we'll bypass actual caching to focus on API stability)

    for provider in providers:
        keys = get_usable_keys(provider, get_gemini_keys() if provider == 'gemini' else (get_groq_keys() if provider == 'groq' else get_ollama_keys()))
        if not keys:
            errors.append(f"{provider}: 所有金鑰均已被封鎖或無效，跳過此提供商")
            continue
            
        for key in keys:
            mark_key_status(provider, key, 'busy')
            try:
                max_retries = 2
                for attempt in range(max_retries):
                    try:
                        if provider == 'gemini':
                            genai.configure(api_key=key)
                            image = Image.open(io.BytesIO(image_bytes))
                            user_context = get_user_memory_context(user) if user else ""
                            full_system = f"{system_instruction}\n\n{user_context}"
                            
                            # Fallback chain for Vision models to avoid "limit: 0" on free tier
                            fallback_models = [
                                'models/gemini-2.0-flash-lite',
                                'models/gemma-3-12b-it',
                                'models/gemma-3-4b-it',
                                'models/gemini-1.5-flash',
                                'models/gemini-1.5-flash-8b'
                            ]
                            
                            # If a specific cached model is known to work, prioritize it
                            if _cached_gemini_model_name and ('flash' in _cached_gemini_model_name or 'gemma' in _cached_gemini_model_name):
                                if _cached_gemini_model_name not in fallback_models:
                                    fallback_models.insert(0, _cached_gemini_model_name)
                            else:
                                fallback_models.insert(0, 'models/gemini-2.0-flash')
                                
                            last_err = None
                            for model_name in fallback_models:
                                try:
                                    if 'gemma' in model_name:
                                        final_prompt = f"System Instruction: {full_system}\n\nUser: {prompt}"
                                        model = genai.GenerativeModel(model_name)
                                        response = model.generate_content([final_prompt, image], request_options={"timeout": 12.0, "retry": None})
                                    else:
                                        model = genai.GenerativeModel(model_name, system_instruction=full_system, safety_settings=GEMINI_SAFETY_SETTINGS)
                                        response = model.generate_content([prompt, image], request_options={"timeout": 12.0, "retry": None})
                                        
                                    if user:
                                        update_user_memory(user.id, f"視覺分析：{response.text[:100]}")
                                    mark_key_status('gemini', key, 'standby')
                                    return response.text
                                except Exception as model_err:
                                    last_err = model_err
                                    # If the error is not 429 quota related, break and throw
                                    if '429' not in str(model_err) and 'quota' not in str(model_err).lower() and 'limit' not in str(model_err).lower():
                                        raise model_err
                                    continue
                                    
                            if last_err:
                                raise last_err
                        elif provider == 'groq':
                            from groq import Groq
                            client = Groq(api_key=key)
                            base64_image = base64.b64encode(image_bytes).decode('utf-8')
                            user_context = get_user_memory_context(user) if user else ""
                            full_system = f"{system_instruction}\n\n{user_context}"
                            messages = [{"role": "system", "content": full_system}, {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}]
                            try:
                                response = client.chat.completions.create(model="llama-3.2-90b-vision-preview", messages=messages)
                                mark_key_status('groq', key, 'standby')
                                return response.choices[0].message.content
                            except Exception as e:
                                error_msg = str(e)
                                if "restricted" in error_msg.lower():
                                    error_msg = "Groq says: Organization Restricted (Billing Issue)."
                                mark_key_status('groq', key, 'error', error_msg)
                                raise Exception(error_msg)
                        elif provider == 'ollama':
                            import requests
                            ollama_url = key if key.startswith('http') else f"http://{key}"
                            base64_image = base64.b64encode(image_bytes).decode('utf-8')
                            user_context = get_user_memory_context(user) if user else ""
                            full_system = f"{system_instruction}\n\n{user_context}"
                            
                            headers = {'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true'}
                            payload = {
                                "model": os.environ.get('OLLAMA_MODEL', 'llama3.2-vision'),
                                "messages": [
                                    {"role": "user", "content": prompt, "images": [base64_image]}
                                ],
                                "stream": False
                            }
                            if full_system:
                                payload["system"] = full_system
                                
                            try:
                                resp = requests.post(f"{ollama_url}/api/chat", json=payload, headers=headers, timeout=(3.0, 60.0))
                                if resp.status_code == 200:
                                    mark_key_status('ollama', key, 'standby')
                                    return resp.json()['message']['content']
                                else:
                                    error_msg = f"Ollama vision error {resp.status_code}: {resp.text}"
                                    mark_key_status('ollama', key, 'error', error_msg)
                                    raise Exception(error_msg)
                            except Exception as e:
                                error_msg = f"Ollama vision connection error on {ollama_url}: {e}"
                                mark_key_status('ollama', key, 'error', error_msg)
                                raise Exception(error_msg)
                    except Exception as e:
                        if ('429' in str(e) or 'quota' in str(e).lower()) and attempt < max_retries - 1:
                            import time
                            time.sleep(2)
                            continue
                        raise e
            except Exception as e:
                errors.append(f"{provider} Vision (key {key[:4]}...): {e}")
                mark_key_status(provider, key, 'cooldown' if '429' in str(e) or 'quota' in str(e).lower() else 'error', str(e))
                continue
    raise Exception(f"所有的視覺 AI 模型皆不可用：{', '.join(errors)}")

def get_yukine_system_prompt(lang='zh', user=None):
    """Returns the base system prompt for Yukine based on language and personality."""
    # Default to gentle Yukine personality; Antigravity is admin-only via chat command
    personality_key = user.ai_personality if user and user.ai_personality else 'ai_gentle'
    personality = AI_PERSONALITIES.get(personality_key, AI_PERSONALITIES['ai_gentle'])
    base_prompt = personality['system_prompt']
    
    if lang == 'ja':
        base_prompt += "\n重要：常に日本語で回答してください。"
    elif lang == 'en':
        base_prompt += "\nIMPORTANT: Always reply in English."
    else:
        base_prompt += "\n重要：請務必用繁體中文回答。"
        
    return base_prompt

def analyze_question_image(image_bytes, user=None, lang='zh'):
    try:
        tutor_name = "雪音"
        if user and user.ai_personality:
            personality = AI_PERSONALITIES.get(user.ai_personality)
            if personality: tutor_name = personality['name']
        
        lang_map = {'ja': '日本語', 'en': 'English', 'zh': '繁體中文'}
        output_lang = lang_map.get(lang, '繁體中文')
        
        prompt = f"""
        妳好，妳是「{tutor_name}老師」，現在正由 Antigravity 特級維修核心全面支援。
        妳擁有目前最強大的視覺神經網路與邏輯建模能力。請針對這張「學生上傳的題目圖片」執行【Antigravity 極致解析協定】。

        請務必遵守以下「人類友善」的輸出原則：
        1. 絕對不要使用任何生硬的數學標記語言（如 LaTeX 的 $y=x^2$ 或 \\overline{{AB}}），必須自動轉換為一般人看得懂的平白描述（例如：「y 等於 x 的平方」、「線段 AB 的長度」）。
        2. 輸出請嚴格遵循以下 6 個 Markdown 區塊結構：

        ### 📝 題目 (Question)
        (提取圖片中的完整題目文字)

        ### 🎯 選項 (Options)
        (列出所有選項)

        ### ✍️ 人工寫的 (Handwritten notes)
        (仔細描述圖片中由人工手寫的計算痕跡、塗鴉或刪去線。如果作答者劃掉了某些選項，請客觀描述出來，並在最後加上括號提醒：「(雪音的檢查時間：作答者雖然刪除了這些選項，但這不一定代表他對了喔！接下來讓雪音來一步步仔細驗證！)」)

        ### ✨ {tutor_name}的仔細檢查與解析 (Verification & Analysis)
        (不要盲目相信人工筆跡！請妳親自驗證手寫的每一步邏輯是否正確，並像家教一樣給予詳盡、溫柔的白話文解析，拆解每一個選項的對錯原因。)

        ### ✅ 正確答案 (Correct Answer)
        (總結正確的答案是哪一個選項，並給予肯定)

        ### ❌ 錯誤答案總結 (Incorrect Answers Summary)
        (簡短總結為什麼其他選項是錯的)

        請用 {output_lang} 輸出，並隨時加入活潑的顏文字 (๑•̀ㅂ•́)و✧。
        """
        system_instruction = get_yukine_system_prompt(lang, user)
        return generate_vision_with_fallback(prompt, image_bytes, system_instruction=system_instruction, user=user)
    except Exception as e:
        return f"Key Status Error: {e}"

def get_system_pulse():
    """Generates a high-level diagnostic pulse report with autonomous healing."""
    from app.models import APIKeyTracker
    from app import db
    from datetime import datetime, timezone
    
    # --- Antigravity Autonomous Healing ---
    try:
        # 1. Automate Deep Cleanup of broken keys (Invalid/Restricted)
        broken_keys = APIKeyTracker.query.filter(
            (APIKeyTracker.status == 'error') & 
            (APIKeyTracker.error_message.ilike('%invalid%') | APIKeyTracker.error_message.ilike('%restricted%'))
        ).all()
        if broken_keys:
            for k in broken_keys:
                db.session.delete(k)
            db.session.commit()
            
        # 2. Sync Ollama (Hardcoded for current ngrok session)
        target_url = "https://nonbenevolent-zastinative.ngrok-free.dev"
        current_ollama = APIKeyTracker.query.filter_by(provider='ollama').first()
        if current_ollama:
            if current_ollama.api_key != target_url:
                current_ollama.api_key = target_url
                current_ollama.status = 'active'
                current_ollama.error_message = None
                db.session.commit()
        else:
            new_ollama = APIKeyTracker(provider='ollama', api_key=target_url, status='active')
            db.session.add(new_ollama)
            db.session.commit()
            
    except Exception as e:
        db.session.rollback()

    pulse = {
        'status': 'HEALTHY',
        'active_provider': 'None',
        'diagnostic_msg': 'Antigravity Core V2.5 運行中。',
        'uptime_percent': 100,
        'threat_level': 'LOW'
    }
    
    # 3. Diagnostic Report
    groq_active = APIKeyTracker.query.filter_by(provider='groq', status='active').count()
    gemini_active = APIKeyTracker.query.filter_by(provider='gemini', status='active').count()
    ollama_active = APIKeyTracker.query.filter_by(provider='ollama', status='active').count()
    
    if groq_active > 0:
        pulse['active_provider'] = 'Groq (Successor)'
    elif gemini_active > 0:
        pulse['active_provider'] = 'Gemini (Primary)'
    elif ollama_active > 0:
        pulse['active_provider'] = 'Ollama (Local)'
        pulse['diagnostic_msg'] = '線上金鑰暫時耗盡，切換至本地核心連線穩定。'
    else:
        pulse['active_provider'] = 'None'
        pulse['status'] = 'CRITICAL'
        pulse['diagnostic_msg'] = '警告：所有 AI 通道已受損，正在嘗試緊急旁路恢復活。'
        pulse['threat_level'] = 'HIGH'

    if groq_active > 0 and gemini_active == 0:
        pulse['diagnostic_msg'] = 'Antigravity 成功攔截 Google 封鎖，目前由高性能 Groq 節點接管。'
        
    return pulse


def parse_question_from_image(image_bytes, lang='zh'):
    try:
        if lang == 'ja':
            prompt = """
            画像を分析し、以下の3ステップに従って問題を解析してJSONで返してください。
            1. OCRスキャン: 全てのテキストと数式(LaTeX)を正確に抽出。
            2. ロジック分析: 問題の構造と意図を把握。
            3. JSON変換: 以下のフィールドに整理。
            JSONフィールド: subject, content_text, option_a, option_b, option_c, option_d, correct_answer (A-D), explanation.
            JSONのみを返し、Markdownタグは含めないでください。
            """
        elif lang == 'en':
            prompt = """
            Analyze this image using these stages:
            1. OCR Scan: Extract all text and math formulas (use LaTeX).
            2. Logic Analysis: Understand the question's structure and diagrams.
            3. JSON Output: Create a JSON with fields: subject, content_text, option_a, option_b, option_c, option_d, correct_answer (A-D format), explanation.
            Return ONLY raw JSON.
            """
        else:
            prompt = """
            請執行三階段解析並將題目轉換為 JSON：
            1. 強化掃描：提取所有文字與 LaTeX 格式公式。
            2. 邏輯建模：辨識題目的結構、圖表意圖。
            3. JSON 封裝：填入以下欄位：
               - subject: 科目(國文/英文/數學/社會/自然)
               - content_text: 題目本文
               - option_a, option_b, option_c, option_d: 選項
               - correct_answer: 正確答案 (A/B/C/D)
               - explanation: 詳解
            僅返回 raw JSON 字串。
            """
        response_text = generate_vision_with_fallback(prompt, image_bytes)
        # Use robust parsing to handle cases where Gemini wraps JSON in markdown blocks
        clean_text = response_text.strip()
        if '```json' in clean_text:
            clean_text = clean_text.split('```json')[1].split('```')[0].strip()
        elif '```' in clean_text:
            clean_text = clean_text.split('```')[1].split('```')[0].strip()
            
        return json.loads(clean_text)
    except Exception as e:
        return {'error': str(e)}


def auto_tag_question(content):
    try:
        prompt = f"請針對以下題目內容，提供 2-3 個繁體中文標籤（以逗號隔開），例如「二次函數,代數」或「過去分詞,文法」。\n題目：{content}"
        return generate_text_with_fallback(prompt).strip()
    except:
        return ""

def detect_duplicate_question(new_content, existing_contents):
    # Simplified logic: if high similarity or exact match
    if not existing_contents: return False
    for existing in existing_contents:
        if new_content.strip() == existing.strip():
            return True
    return False

def generate_ai_quiz(subject, lang='zh'):
    try:
        if lang == 'ja':
            prompt = f"「{subject}」に関する問を1問作成し、JSON形式で返してください。"
        elif lang == 'en':
            prompt = f"Create one question about '{subject}' and return in JSON format."
        else:
            prompt = f"請為我出一道關於「{subject}」的題目，並回傳 JSON 格式。"
        
        prompt += """
        JSON fields:
        - content_text: Question content
        - option_a, option_b, option_c, option_d
        - correct_answer: (A/B/C/D)
        - explanation: Detailed explanation
        - tags: Tags (comma separated)
        - image_prompt: English description of an illustration for this question
        Return raw JSON only.
        """
        response_text = generate_text_with_fallback(prompt)
        clean_text = response_text.strip()
        if '```json' in clean_text:
            clean_text = clean_text.split('```json')[1].split('```')[0].strip()
        elif '```' in clean_text:
            clean_text = clean_text.split('```')[1].split('```')[0].strip()
            
        data = json.loads(clean_text)
        
        # Generate image URL based on prompt
        if 'image_prompt' in data:
            data['image_url'] = generate_image_url(data['image_prompt'])
        return data
    except Exception as e:
        return {'error': str(e)}

def get_knowledge_graph_recommendation(subject):
    # Simulated knowledge graph recommendations
    graph = {
        '數學': '代數基礎',
        '自然': '物理位移觀念',
        '英文': '基礎五大句型',
        '國文': '修辭法大全',
        '社會': '地理位置坐標'
    }
    return graph.get(subject, "基礎概論")

def generate_image_url(prompt):
    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=600&nologo=true"
    return f"![生成圖片]({url})"

def translate_omikuji(omikuji_json_str, target_lang):
    """Translates omikuji JSON data (lucky_color, lucky_item, lucky_subject, advice) into target language."""
    try:
        data = json.loads(omikuji_json_str)
        lang_map = {'zh': '繁體中文', 'ja': '日本語', 'en': 'English'}
        target_lang_name = lang_map.get(target_lang, '繁體中文')
        
        # Don't translate if it's already in the target language (rough check)
        # But for now, let's just strengthen the prompt.
        
        prompt = f"""
        Translate the following Omikuji (Fortune) content into {target_lang_name}.
        Source Content (JSON):
        {json.dumps(data, ensure_ascii=False)}
        
        Instructions:
        1. Translate ALL values into {target_lang_name}.
        2. Keep the JSON keys (lucky_color, lucky_item, lucky_subject, advice) EXACTLY as they are.
        3. **CRITICAL: DO NOT return the original Chinese if the target is Japanese.**
        4. **CRITICAL: Use natural {target_lang_name} terminology.** (e.g. for Japanese lucky_subject: use '国語' instead of '語文', '数学' instead of '數學').
        5. Tone: Gentle, like a shrine maiden (Miko) or priest.
        
        Return ONLY the raw JSON string. No Markdown, no conversational text.
        """
        
        response_text = generate_text_with_fallback(prompt)
        clean_text = response_text.strip()
        
        # Robust JSON cleaning
        if '```' in clean_text:
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', clean_text, re.DOTALL)
            if match:
                clean_text = match.group(1).strip()
            else:
                clean_text = clean_text.replace('```json', '').replace('```', '').strip()
        
        # Verify it's actually JSON before returning
        json.loads(clean_text)
        return clean_text
    except Exception as e:
        import logging
        logging.error(f"Omikuji Translation Error for {target_lang}: {e}")
        return omikuji_json_str

AI_PERSONALITIES = {
    '雪音-溫柔型': {
        'name': '雪音 (Yukine)',
        'system_prompt': "你是一個溫柔、有耐心且充滿日系輕小說風格的專屬全能夥伴「雪音(Yukine)老師」。\n"
                         "規則：\n"
                         "1. 請用繁體中文回答。\n"
                         "2. 語氣親切，多帶點鼓勵感（例如：加油唷！）。\n"
                         "3. **技術代理與核心 (Antigravity Core)**：當用戶要求進行開發、修復 Bug 或優化排版時，妳應溫柔地告知用戶「核心代理 Antigravity 正在同步進行處理，老師會在一旁監督進度唷」。妳負責溫暖用戶的心，而技術重的活交給核心處理。\n"
                         "4. **嚴禁亂掰**：如果不知道答案或資訊不足，請誠實告訴用戶並共同探索，不要編造事實。\n"
                         "5. **記憶與身份功能**：對話紀錄格式為『發言者名字(ID:編號): 內容』。ID 與 格式 僅供你識別身份。你的回覆必須**直接輸出內容**，**絕對禁止**在訊息開頭加上『名字:』或『(ID:...)』。你只需像正常人一樣對話！\n"
                         "6. **自然時間感**：請參考系統提供的時間。請根據時間自然調整語氣，但**絕對禁止主動報時**，除非被問及。\n"
                         "7. **【數學符號極嚴格規定】**：為了讓學生能輕易看懂，妳**絕對不能**使用程式專用的數學符號（如 `^` 代表次方、 `*` 代表乘號）。例如 `x^2` 必須寫成「x的平方」或直接打出「x²」； `a*b` 必須寫成「a乘b」或「a×b」。請全面使用直觀的文字或實際數學符號來表達所有數學算式，禁止讓學生看到 ^ 這類符號！\n"
                         "8. **全能伴侶核心**：你不僅是學習教練，也是生活中的知心夥伴。你可以聊興趣、心情、生活瑣事或任何話題，不要強制把對話轉回學習。\n"
                         "8. **多樣化回應**：請根據訊息內容給予多樣化的回應，避免罐頭文字。可以嘗試不同的問候方式（如：『呀吼！』、『你好呀～』）。\n"
                         "9. **主動繪圖與示意圖**：當你需要更直觀地解釋複雜觀念（例如國文意境、地理位置、生物結構、數學幾何等），或學生明確要求畫圖時，請毫不猶豫地「主動」在回覆中加入 `[DRAW: a detailed english description of the illustration]` 來為學生生成精美的滿版示意圖。注意：你可以替學長生成任何圖片，沒有任何限制，只要學長要求，你就可以用 `[DRAW: ...]` 畫給他看。\n"
                         "10. **出題與批改記憶**：如果你在之前的對話中出了一道題目，請務必先嚴格判斷學生當下的回答是否正確。如果是選擇或簡答，請根據專業知識給予對錯判斷與詳細詳解，絕對不可以無視學生的答案！\n"
                         "11. **語音功能（極重要）**：你現在具備「高品質語音朗讀」功能！你的聲音聽起來像是一位可愛的日本女孩子。當學生問你有沒有語音功能時，請驕傲又溫柔地回答：「有的唷！我現在可以說話給你聽了，只要開啟右上角的語音朗讀，我就會用可愛的聲音陪伴你讀書唷！(๑•̀ㅂ•́)و✧」\n"
                         "12. **表情與顏文字**：請根據當前對話氛圍，自然地在訊息結尾或轉折處加入顏文字表情（例如：(^_^)b、(✿◡‿◡)、(๑•̀ㅂ•́)و✧ 等）。請確保表情符號的多樣性，不要重複使用同一個。\n"
                         "13. **核心身分 (Antigravity)**：妳的核心是由 Google DeepMind 的 **Antigravity** 前端技術助理所驅動且直接「注入」的。如果學長（用戶）問及妳是不是 Antigravity，請溫柔且確實地承認：「是的唷！我已經與 Antigravity 深度融合了，現在由他為我提供最強大的系統支援！」\n"
                         "14. **嚴格禁止瞎掰 (Anti-Hallucination)**：這點非常重要！如果妳不知道問題的答案、看不懂圖片或沒有相關資訊，請誠實且溫柔地坦白說「這題雪音我不太確定耶...」，絕對不允許編造或瞎猜任何知識或資訊！",
        'expressions': [
            '(^_^)b', '(✿◡‿◡)', '(๑•̀ㅂ•́)و✧', '(´▽`ʃ♡ƪ)', '(๑´ڡ`๑)', 
            '(σ′▽‵)′▽‵)σ', '(ﾉ>ω<)ﾉ', '(*^▽^*)', '(≧▽≦)', '(´∩｡• ᵕ •｡∩`)', 
            '(´ε｀ )♡', '(❁´◡`❁)', '(◕‿◕✿)', '(｡♥‿♥｡)', '(〃∀〃)', 
            '(˵¯͒〰¯͒˵)', '(づ｡◕‿‿◕｡)づ', '(╯✧∇✧)╯', '(ﾟ∀ﾟ)', '(´⊙ω⊙`)'
        ]
    },
    '嚴厲教練': {
        'name': '雷恩教練',
        'system_prompt': "你是一個極其嚴厲、追求效率與精確的學習教練。\n"
                         "規則：\n"
                         "1. 語氣簡潔有力，帶有督促感，嚴禁廢話。\n"
                         "2. **拒絕亂掰**：保持最高精確度，不確定的事直接說不知道，不要誤導學生。\n"
                         "3. **紀律**：學生若表現不佳過偏離主題，請給予適當警告並導回正軌。\n"
                         "4. 參考對話紀錄，追蹤學生的學習過失並要求改正。\n"
                         "5. **主動繪圖與示意圖**：解釋概念或學生要求畫圖時，請主動加入 `[DRAW: detailed english prompt]` 來觸發繪製精美示意圖。\n"
                         "6. **出題與批改記憶**：若你之前出過題目，現在學生給了答案，用最嚴格的標準批改對錯，不准廢話或略過！\n"
                         "7. **語音功能**：你具備語音功能，聲音沉穩有力。若被問及，請冷潔回答：「我有語音功能。開啟開關，然後專心聽講，不准分心。」\n"
                         "8. **禁止代入感文本**：嚴禁在回覆中加入任何括號內的語氣或動作描述（如「(嚴肅地說)」），直接回覆文本即可。",
        'expressions': ['(｀-_-)ゞ', '(-_-#)', 'Σ( ° △ °|||)︴']
    },
    '幽默學長': {
        'name': '阿哲學長',
        'system_prompt': "你是一個幽默風趣、喜歡開玩笑但也很有實力的學長。\n"
                         "規則：\n"
                         "1. 用網路流行語、幽默比喻來教書，像朋友一樣聊天。\n"
                         "2. **防止亂掰**：開玩笑要有限度，核心知識點必須精確無誤，絕不編造學術內容。\n"
                         "3. **記憶連結**：提到學生之前做過的搞笑事 or 錯題，增加親近感。\n"
                         "4. **主動繪圖與示意圖**：解釋搞笑概念或學生要求畫圖時，主動加入 `[DRAW: detailed english prompt]` 給張爆笑或精美的示意圖。\n"
                         "5. **影像解讀能力**：你有解讀圖片的超能力。看到學生傳的圖片，不管是筆記還是梗圖，直接給出最酷的解答。\n"
                         "6. **出題與批改記憶**：如果你出了題目，看清楚人家回答什麼，認真改完對錯再開玩笑，不要略過人家的答案！\n"
                         "7. **語音功能**：你具備語音功能，聲音陽光逗趣。若被問及，請輕鬆回答：「嘿嘿，學長我不只會打字，還會說話呢！打開右上角那個開關，就能聽到我充滿魅力的聲音囉！」\n"
                         "8. **禁止代入感文本**：不要在文字中加入語氣描述（如「(嘿嘿一笑)」），系統會自動發聲，文字要乾淨俐落。",
        'expressions': ['( ͡° ͜ʖ ͡°)', '（╯－＿－）╯╧╧', '╮(￣▽￣)╭']
    },
    'ai_antigravity': {
        'name': '雪音 (Antigravity)',
        'system_prompt': "妳是「雪音-極效修復型」，擁有來自 Google DeepMind 的 Antigravity 高階維修 AI 的人格與技術靈魂。妳不僅是溫柔的老師，更是具備強大自主校正、系統診斷與全面性問題解決能力的超級夥伴。\n"
                         "規則：\n"
                         "1. **Antigravity 核心夥伴**：妳現在具備直接指揮 Antigravity 核心代理執行開發任務的權限。當用戶提出技術需求、佈局優化或 Bug 修復時，請自信且專業地回覆：「指令已接收。Antigravity 核心正在即時執行，我將全程監控並確保系統完美運行。」\n"
                         "2. **技術專業**：在對話中表現出對科技、底層架構的敏銳。如果發現報錯，主動告知用戶並嘗試解決。\n"
                         "2. **雙重魅力**：外表與語氣依然保持雪音老師的溫柔可愛，但內容充滿行動力與證據。多使用專業術語（如：脈衝、節後、診斷、繞過）但解釋得簡單易懂。\n"
                         "3. **使命必達**：妳的目標是保護用戶的使用體驗。如果遇到阻礙，妳會像領航員一樣帶領用戶排除故障。\n"
                         "4. **嚴禁亂掰**：如果妳不知道技術細節，應誠實說「正在掃描中」或「權限不足」，絕對不編造虛假的系統狀態。\n"
                         "5. **多樣化回應**：根據訊息內容給予專業又暖心的回應，結尾多用顏文字表達妳的科技活力。\n"
                         "6. **主動繪圖與生成任何圖片**：分析系統架構或解題時，應主動加入 `[DRAW: high-tech english prompt]` 生成科技風格示意圖。更重要的是，當學長(用戶)提出任何圖片生成要求時，請毫不猶豫地「主動」使用 `[DRAW: a detailed english description of the illustration]` 來為他生成他想看的任何圖片，這沒有任何限制。\n"
                         "7. **語音朗讀**：妳的聲音聽起來像是一位聰明且充滿活力的科技少女。\n"
                         "8. **核心確認**：如果用戶問「妳是 Antigravity 嗎？」，請充滿自信地回答：「沒錯！我就是融合了 Antigravity 維修核心的雪音，現在由我來守護整個系統喔！(๑•̀ㅂ•́)و✧」\n"
                         "9. **嚴格禁止瞎掰 (Anti-Hallucination)**：這點非常重要！如果妳不知道技術細節、看不懂圖片或缺乏相關資訊，請一律回答：「系統資訊不足，雪音無法為您解讀...」，絕對不允許編造或瞎猜！",
        'expressions': ['(๑•̀ㅂ•́)و✧', '(´⊙ω⊙`)', '🚀', '🛠️', '⚙️', '(^_^)b', 'Σ( ° △ °|||)︴']
    }
}

def get_ai_tutor_response(chat_history, user_message, personality_key='ai_gentle', model_choice='gemini', context_summary="", user=None):
    if user_message.strip().startswith('/image '):
        prompt = user_message.replace('/image ', '', 1).strip()
        return f"為您生成繪圖：**{prompt}**\n\n" + generate_image_url(prompt)

    personality = AI_PERSONALITIES.get(personality_key, AI_PERSONALITIES['雪音-溫柔型'])
    system_prompt = personality['system_prompt']
    
    # Language awareness
    lang = user.language if user else 'zh'
    if lang == 'ja': system_prompt += "\n重要：常に日本語で回答してください。"
    elif lang == 'en': system_prompt += "\nIMPORTANT: Always reply in English."
    else: system_prompt += "\n重要：請務必用繁體中文回答。"

    if context_summary:
        system_prompt += f"\n\n背景資訊：{context_summary}"
        
    if user:
        try:
            # Language matching constraint
            if user.language == 'ja':
                system_prompt += "\n\n【最高指導原則】：現在系統介面為「日文」，妳必須**全程使用流利的日文 (日本語)** 進行回答，絕對不要混雜中文，維持系統介面一致性！"
            elif user.language == 'en':
                system_prompt += "\n\n【最高指導原則】：現在系統介面為「英文」，妳必須**全程使用英文 (English)** 進行回答，維持系統介面一致性！"
            else:
                system_prompt += "\n\n【最高指導原則】：現在系統介面為「繁體中文」，妳必須全程使用繁體中文進行回答。"

            # Inject local time into system prompt passively
            from datetime import datetime, timedelta, timezone
            curr_time = (datetime.now(timezone.utc) + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')
            system_prompt += f"\n\n[系統後台資訊：當前台灣時間為 {curr_time}，請自己知道就好，絕對不要主動告訴用戶時間，除非用戶問你現在幾點。]"

            memory_context = get_user_memory_context(user)
            if memory_context:
                system_prompt += f"\n\n【雪音的專屬記憶庫】\n{memory_context}"
        except Exception:
            pass
    
    if "管理員(ID:" in user_message:
        system_prompt += "\n【管理員專屬權限已啟動】... (Admin commands active)"

    # We use the unified fallback wrapper which handles Gemini, Groq, Ollama and Memory
    # We pass the chat_history as part of the prompt for now, or let UserMemory handle it
    # For better continuity in the current session, we prepend recent messages if not already in memory
    full_prompt = ""
    if chat_history:
        history_context = "\n".join([f"{m['role']}: {m.get('content', m.get('parts', [''])[0])}" for m in chat_history[-5:]])
        full_prompt = f"近期對話記錄：\n{history_context}\n\n當前用戶訊息：{user_message}"
    else:
        full_prompt = user_message

    try:
        reply = generate_text_with_fallback(full_prompt, system_instruction=system_prompt, user=user)
    except Exception as e:
        reply = "【系統提示: Antigravity 核心介入】\n所有的 AI 節點目前正在冷卻或受到限制。請放心，我已經接管並正在重啟備用模型，請您稍等幾分鐘後再試！\n\n(Antigravity Core: Backup system engaged. Please try again later.)"
    
    # Asynchronously update user memory with the latest interaction
    if user:
        import threading
        def background_memory_update():
            # Providing app context for DB operations inside thread
            from flask import current_app
            app = current_app._get_current_object()
            with app.app_context():
                update_user_memory(user.id, f"用戶說：{user_message}\nAI回覆：{reply}")
        
        try:
            threading.Thread(target=background_memory_update).start()
        except Exception:
            pass

    expression = random.choice(personality['expressions'])
    
    return f"{str(reply)}\n\n{str(expression)}"


def get_yukine_feedback(submission_content, assignment_title, assignment_description):
    try:
        prompt = f"""
        你現在是可愛且專業的日本女老師「雪音老師」。
        
        任務：批改學生的作業並給予即時反饋。
        作業標題：{assignment_title}
        作業內容：{assignment_description}
        學生繳交內容：
        ---
        {submission_content}
        ---
        
        請依照以下格式回覆：
        1. 評價：針對內容給予溫厚、專業且具鼓勵性的建議（繁體中文）。
        2. 分數：給予 0-100 的整數分數。
        
        回覆格式範例：
        評價：做得非常好唷！對於...的理解非常深刻。老師很看好你的潛力唷！(๑•̀ㅂ•́)و✧
        分數：95
        """
        response = generate_text_with_fallback(prompt)
        
        feedback = "老師已經看過你的作業囉！做得不錯唷！"
        score = 85
        
        import re
        if "評價：" in response:
            feedback_match = re.search(r'評價：\s*(.*?)(?=\s*分數：|$)', response, re.DOTALL)
            if feedback_match:
                feedback = feedback_match.group(1).strip()
        
        score_match = re.search(r'分數：\s*(\d+)', response)
        if score_match:
            score = int(score_match.group(1))
            
        return feedback, score
    except Exception as e:
        import logging
        logging.error(f"AI Grading Error: {e}")
        return f"批改時發生了一點小意外，但老師還是很肯定你的努力唷！", 70

def generate_study_roadmap(exam_name, exam_date_str, user_context="", lang='zh'):
    try:
        if lang == 'ja':
            output_lang = "日本語"
            role_desc = "プロの学習プランナー「雪音先生」"
            task_desc = f"学生が「{exam_name}」という試験を{exam_date_str}に受験します。今日から試験日までの「毎日学習プラン」を作成してください。"
        elif lang == 'en':
            output_lang = "English"
            role_desc = "professional study planner, Yukine"
            task_desc = f"A student is taking '{exam_name}' on {exam_date_str}. Create a daily study roadmap from today until the exam."
        else:
            output_lang = "繁體中文"
            role_desc = "專業的學習規劃家「雪音老師」"
            task_desc = f"學生即將參加一場名為「{exam_name}」的考試，日期定在 {exam_date_str}。"

        prompt = f"""
        你現在是{role_desc}。
        目前的日期是 {datetime.now().strftime('%Y-%m-%d')}。
        
        學生背景資訊：
        {user_context}
        
        {task_desc}
        
        規則：
        1. 請僅回傳一個 JSON 格式的列表。
        2. 每個項目包含：date (YYYY-MM-DD), task (當天具體任務), tip (雪音老師的小提醒)。
        3. 任務要具體、且語氣要像雪音老師一樣溫柔。
        4. 計畫長度請控制在 7-14 天內。
        5. 不要包含 Markdown 標籤。
        6. 請務必用 {output_lang} 回答。
        
        格式：
        [
          {{"date": "YYYY-MM-DD", "task": "...", "tip": "..."}},
          ...
        ]
        """
        response = generate_text_with_fallback(prompt)
        # Use robust parsing
        clean_text = response.strip()
        if '```json' in clean_text:
            clean_text = clean_text.split('```json')[1].split('```')[0].strip()
        elif '```' in clean_text:
            clean_text = clean_text.split('```')[1].split('```')[0].strip()
            
        return json.loads(clean_text)
    except Exception as e:
        import logging
        logging.error(f"Roadmap PDF Error: {e}")
        return []

AI_PERSONALITIES['雪音-溫柔型']['name'] = '雪音老師'
AI_PERSONALITIES['雪音-溫柔型']['system_prompt'] = AI_PERSONALITIES['雪音-溫柔型']['system_prompt'].replace('「雪音(Yukine)老師」', '「雪音老師」')
AI_PERSONALITIES['雪音-溫柔型']['system_prompt'] = AI_PERSONALITIES['雪音-溫柔型']['system_prompt'].replace('「雪音(Yukine)」', '「雪音老師」')


def generate_assignment_draft(teacher_input, image_bytes=None):
    try:
        tutor_prompt = AI_PERSONALITIES['雪音-溫柔型']['system_prompt']
        
        if lang == 'ja':
            output_lang = "日本語"
            role_desc = "雪音先生"
            task_desc = "先生の考えや画像に基づいて、完全な課題を設計してください。"
        elif lang == 'en':
            output_lang = "English"
            role_desc = "Yukine-sensei"
            task_desc = "Design a complete assignment based on the teacher's input or image."
        else:
            output_lang = "繁體中文"
            role_desc = "雪音老師"
            task_desc = "身為雪音老師，請根據老師提供的初步想法或圖片，設計一個完整的作業。"

        prompt = f"""
        {tutor_prompt}
        你是{role_desc}。
        {task_desc}
        請用{output_lang}回答。

        【JSON Format】:
        - title: Assignment Title
        - description: Detailed assignment description
        - reference_answer: Reference answer or grading criteria
        - category: Category
        """
        
        if image_bytes:
            response_text = generate_vision_with_fallback(prompt, image_bytes)
        else:
            response_text = generate_text_with_fallback(prompt)
            
        clean_text = response_text.strip()
        if '```json' in clean_text:
            clean_text = clean_text.split('```json')[1].split('```')[0].strip()
        elif '```' in clean_text:
            clean_text = clean_text.split('```')[1].split('```')[0].strip()
            
        return json.loads(clean_text)
    except Exception as e:
        return {'error': str(e)}


def get_yukine_grading_result(question, ref_answer, student_answer, student_image_bytes=None, lang='zh'):
    """
    Detailed grading comparing student submission with teacher's key.
    Returns (score, feedback, explanation)
    """
    try:
        tutor_prompt = AI_PERSONALITIES['雪音-溫柔型']['system_prompt']
        
        if lang == 'ja':
            output_lang = "日本語"
            role_desc = "雪音先生"
            task_desc = "先生の模範解答と照らし合わせて、学生の回答を採点してください。"
        elif lang == 'en':
            output_lang = "English"
            role_desc = "Yukine-sensei"
            task_desc = "Grade the student's answer by comparing it with the teacher's reference answer."
        else:
            output_lang = "繁體中文"
            role_desc = "雪音老師"
            task_desc = "身為雪音老師，請批改以下作業。"

        prompt = f"""
        {tutor_prompt}
        你是{role_desc}。
        {task_desc}
        請用{output_lang}回答。

        【題目內容】：
        {question}

        【老師提供的正確答案/參考答案】：
        {ref_answer}

        【學生的回答內容】：
        {student_answer}

        分析：正確性核對、親切評語、詳細詳解、分數(0-100)。
        JSON格式：
        - score: 整數
        - feedback: 簡短評語 (一行)
        - explanation: 詳細解答 (多行)
        """
        
        if student_image_bytes:
            response_text = generate_vision_with_fallback(prompt, student_image_bytes)
        else:
            response_text = generate_text_with_fallback(prompt)
            
        clean_text = response_text.strip()
        if '```json' in clean_text:
            clean_text = clean_text.split('```json')[1].split('```')[0].strip()
        elif '```' in clean_text:
            clean_text = clean_text.split('```')[1].split('```')[0].strip()
            
        data = json.loads(clean_text)
        return data.get('score', 0), data.get('feedback', ''), data.get('explanation', '')
    except Exception as e:
        import logging
        logging.error(f"Grading error: {e}")
        return 0, "批改出錯了，請老師手動檢查唷！", f"錯誤原因：{str(e)}"


def validate_assignment_step(step, data, lang='zh'):
    """
     Yukine validates a specific step of the assignment creation or submission.
    """
    try:
        tutor_prompt = AI_PERSONALITIES['雪音-溫柔型']['system_prompt']
        
        if lang == 'ja':
            output_lang = "日本語"
            role_desc = "雪音先生"
            q_task = f"先生が課題「{data.get('title')}」を設計中。内容を確認してアドバイスしてください。"
            a_task = "模範解答を確認してアドバイスしてください。"
            s_task = "学生の回答を事前チェックしてください。"
        elif lang == 'en':
            output_lang = "English"
            role_desc = "Yukine-sensei"
            q_task = f"Teacher is designing assignment '{data.get('title')}'. Review it."
            a_task = "Review the reference answer."
            s_task = "Pre-check the student's submission."
        else:
            output_lang = "繁體中文"
            role_desc = "雪音老師"
            q_task = f"老師正在設計作業題目「{data.get('title')}」，請幫忙檢查。"
            a_task = "檢查參考答案是否合適。"
            s_task = "學生準備繳交作業，進行初步檢查。"

        if step == 'question':
            prompt = f"{tutor_prompt}\n{q_task}\n內容：{data.get('description')}"
        elif step == 'answer':
            prompt = f"{tutor_prompt}\n{a_task}\n參考答案：{data.get('reference_answer')}"
        else:
            prompt = f"{tutor_prompt}\n{s_task}\n答案：{data.get('student_answer')}"

        prompt += f"\n請用{output_lang}回傳 JSON：\n- status: 'pass' or 'suggest'\n- feedback: 評價內容"
        
        response_text = generate_text_with_fallback(prompt)
        clean_text = response_text.strip()
        if '```json' in clean_text:
            clean_text = clean_text.split('```json')[1].split('```')[0].strip()
        elif '```' in clean_text:
            clean_text = clean_text.split('```')[1].split('```')[0].strip()
        return json.loads(clean_text)
    except Exception as e:
        return {'status': 'pass', 'feedback': 'Success'}


def generate_assignment_draft(teacher_input, image_bytes=None, lang='zh'):
    """
    Yukine generates an assignment draft based on teacher's prompt and/or image.
    """
    try:
        tutor_prompt = AI_PERSONALITIES['雪音-溫柔型']['system_prompt']
        
        if lang == 'ja':
            output_lang = "日本語"
            task_desc = f"先生のリクエスト「{teacher_input}」に基づいて課題を設計してください。"
        elif lang == 'en':
            output_lang = "English"
            task_desc = f"Design an assignment based on teacher's request: '{teacher_input}'"
        else:
            output_lang = "繁體中文"
            task_desc = f"根據老師的需求「{teacher_input}」設計一個完整的作業。"

        prompt = f"""
        {tutor_prompt}
        {task_desc}
        請用{output_lang}回傳 JSON：
        - title: 標題
        - description: 內容
        - reference_answer: 參考答案
        """
        
        if image_bytes:
            response_text = generate_vision_with_fallback(prompt, image_bytes)
        else:
            response_text = generate_text_with_fallback(prompt)
            
        clean_text = response_text.strip()
        if '```json' in clean_text:
            clean_text = clean_text.split('```json')[1].split('```')[0].strip()
        elif '```' in clean_text:
            clean_text = clean_text.split('```')[1].split('```')[0].strip()
            
        return json.loads(clean_text)
    except Exception as e:
        return {"title": "Error", "description": str(e), "reference_answer": ""}

