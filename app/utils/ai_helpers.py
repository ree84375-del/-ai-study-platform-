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
    gemini_keys = get_gemini_keys()
    groq_keys = get_groq_keys()
    ollama_keys = get_ollama_keys()
    
    # Sync all current keys to DB
    _sync_keys_to_db('gemini', gemini_keys)
    _sync_keys_to_db('groq', groq_keys)
    _sync_keys_to_db('ollama', ollama_keys)
    
    # Perform Auto-Repair here
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
            
    # SYSTEM-WIDE RECOVERY PULSE:
    # If a key stays in 'error' or 'cooldown' for more than 30 seconds, 
    # force it back to standby. We want to be very aggressive in retrying.
    for t in trackers:
        if t.status in ['cooldown', 'error']:
            if not t.cooldown_until or t.cooldown_until < now:
                t.status = 'standby'
                t.error_message = None
                t.cooldown_until = None
    
    # SPECIAL CASE: Skip Restricted Keys from Recovery
    for t in trackers:
        if t.error_message and "restricted" in t.error_message.lower():
            t.status = 'error' # Stay in error
            t.cooldown_until = now + timedelta(days=1)
    
    try:
        if db.session.is_modified():
            db.session.commit()
    except Exception:
        db.session.rollback()
    
    masked_status = {'gemini': [], 'groq': [], 'ollama': []}
    trackers = APIKeyTracker.query.all()
    
    all_env_keys = gemini_keys + groq_keys + ollama_keys
    
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
    elif status in ['cooldown', 'error']:
        tracker.error_message = error
        # Exponential backoff for 429 errors
        if error and ('429' in error or 'quota' in error.lower()):
            tracker.retry_count = (tracker.retry_count or 0) + 1
            minutes = min(5 * (2 ** (tracker.retry_count - 1)), 120) # 5m, 10m, 20m... max 2h
            tracker.cooldown_until = now + timedelta(minutes=minutes)
        else:
            # Generic error fixed cooldown (Reduced from 30m to 2m for better recovery)
            tracker.cooldown_until = now + timedelta(minutes=2)
            
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()

def get_usable_keys(provider, base_keys):
    if not base_keys: return []
    try:
        # Trigger auto-repair sweep
        get_all_api_key_statuses()
        
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
                
            # DO NOT EVER use keys that have "restricted" in the error message (Billings/Ban)
            if t.error_message and "restricted" in t.error_message.lower():
                continue
                
            if t.status == 'standby':
                # Double check cooldown_until just in case
                if not t.cooldown_until or t.cooldown_until < now:
                    usable.append(k)
            elif t.status == 'active':
                # Active keys are usually fine to reuse if not busy
                usable.append(k)
        
        # SELF-HEALING FALLBACK: If all keys are in cooldown/error, don't just give up.
        # Fallback to the original base_keys and let the try/except block in generation handle the failure.
        # This prevents the UI from just showing "All keys dead" if some are actually recovered but not synced yet.
        return usable if usable else base_keys
    except Exception:
        try:
            db.session.rollback()
        except: pass
        return base_keys


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
    providers = ['gemini', 'groq', 'ollama']
    random.shuffle(providers)
    
    errors = []
    for provider in providers:
        keys = get_usable_keys(provider, get_gemini_keys() if provider == 'gemini' else (get_groq_keys() if provider == 'groq' else get_ollama_keys()))
        for key in keys:
            # Busy-Locking
            mark_key_status(provider, key, 'busy')
            try:
                # Retry logic for 429 errors
                max_retries = 2
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
                                
                            response = model.generate_content(final_prompt)
                            mark_key_status('gemini', key, 'active')
                            if user:
                                update_user_memory(user.id, f"用戶：{prompt[:80]} -> 雪音：{response.text[:80]}")
                            return response.text
                        elif provider == 'groq':
                            from groq import Groq
                            client = Groq(api_key=key)
                            user_context = get_user_memory_context(user) if user else ""
                            full_system = f"{system_instruction}\n\n{user_context}"
                            messages = [{"role": "system", "content": full_system}, {"role": "user", "content": prompt}]
                            response = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages)
                            mark_key_status('groq', key, 'active')
                            if user:
                                update_user_memory(user.id, f"用戶：{prompt[:80]} -> 雪音(Groq)：{response.choices[0].message.content[:80]}")
                            return response.choices[0].message.content
                        elif provider == 'ollama':
                            import requests
                            # Use specific headers to bypass ngrok browser warnings
                            headers = {'Content-Type': 'application/json', 'ngrok-skip-browser-warning': 'true'}
                            try:
                                ollama_url = key if key.startswith('http') else f"http://{key}"
                                # Test connection with timeout
                                requests.get(f"{ollama_url}/api/tags", timeout=3, headers=headers)
                                
                                payload = {
                                    "model": os.environ.get('OLLAMA_MODEL', 'llama3.2:latest'),
                                    "messages": [{"role": "user", "content": prompt}],
                                    "stream": False
                                }
                                resp = requests.post(f"{ollama_url}/api/chat", json=payload, timeout=30, headers=headers)
                                if resp.status_code == 200:
                                    mark_key_status('ollama', key, 'active')
                                    return resp.json()['message']['content']
                                else:
                                    error_msg = f"Ollama error {resp.status_code}: {resp.text}"
                                    mark_key_status('ollama', key, 'error', error_msg)
                                    raise Exception(error_msg)
                            except Exception as e:
                                error_msg = f"Ollama connection error on {ollama_url}: {e}"
                                mark_key_status('ollama', key, 'error', error_msg)
                                raise Exception(error_msg)
                    except Exception as e:
                        if ('429' in str(e) or 'quota' in str(e).lower()) and attempt < max_retries - 1:
                            import time
                            time.sleep(2) # Short wait before retry
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
    providers = ['gemini', 'groq', 'ollama']
    random.shuffle(providers)
    errors = []
    
    # Simple Hash-based Cache (Saves API Quota)
    import hashlib
    img_hash = hashlib.md5(image_bytes).hexdigest()
    cache_key = f"vision_cache_{img_hash}_{hashlib.md5(prompt.encode()).hexdigest()}"
    # (In a real app, use Redis/DB. For now, we'll bypass actual caching to focus on API stability)

    for provider in providers:
        keys = get_usable_keys(provider, get_gemini_keys() if provider == 'gemini' else (get_groq_keys() if provider == 'groq' else get_ollama_keys()))
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
                            
                            # Use Flash by default for vision to save quota
                            model_name = _cached_gemini_model_name if _cached_gemini_model_name and 'flash' in _cached_gemini_model_name else 'models/gemini-1.5-flash'
                            model = genai.GenerativeModel(model_name, system_instruction=full_system, safety_settings=GEMINI_SAFETY_SETTINGS)
                            
                            response = model.generate_content([prompt, image])
                            mark_key_status('gemini', key, 'active')
                            if user:
                                update_user_memory(user.id, f"視覺分析：{response.text[:100]}")
                            return response.text
                        elif provider == 'groq':
                            from groq import Groq
                            client = Groq(api_key=key)
                            base64_image = base64.b64encode(image_bytes).decode('utf-8')
                            user_context = get_user_memory_context(user) if user else ""
                            full_system = f"{system_instruction}\n\n{user_context}"
                            messages = [{"role": "system", "content": full_system}, {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}]
                            try:
                                response = client.chat.completions.create(model="llama-3.2-90b-vision-preview", messages=messages)
                                mark_key_status('groq', key, 'active')
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
                                resp = requests.post(f"{ollama_url}/api/chat", json=payload, headers=headers, timeout=60)
                                if resp.status_code == 200:
                                    mark_key_status('ollama', key, 'active')
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
    personality_key = user.ai_personality if user and user.ai_personality else '雪音-溫柔型'
    personality = AI_PERSONALITIES.get(personality_key, AI_PERSONALITIES['雪音-溫柔型'])
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
        你是「{tutor_name}老師」，一位擁有強大視覺分析能力的全能導師。
        請根據圖片內容執行以下【三階段強化分析】：
        
        **階段一：精準掃描 (OCR)**
        - 辨識圖片中所有的文字、符號、公式。
        - 數學公式請務必轉換為 LaTeX 格式（例如：$x^2 + y^2 = r^2$）。
        - 描述所有可見的圖表、座標軸、幾何圖形。
        
        **階段二：結構化邏輯建模**
        - 分析圖片中文字與圖形的空間關係（例如：文字 A 是在指涉圖形 B 的長度）。
        - 判斷該情境（這是一張考卷、黑板隨拍、還是筆記本上的速記？）。
        
        **階段三：深度解析與互動**
        - 如果是學術題目，請給予詳細且具備教學溫度的解題引導。
        - 提供與該內容相關的進階知識點或建議。
        
        請用 {output_lang} 回答，排版需優雅且結構化，請加入親切的顏文字 (๑•̀ㅂ•́)و✧。
        """
        system_instruction = get_yukine_system_prompt(lang, user)
        return generate_vision_with_fallback(prompt, image_bytes, system_instruction=system_instruction, user=user)
    except Exception as e:
        return f"Key Status Error: {e}"

def get_system_pulse():
    """Generates a high-level diagnostic pulse report from Antigravity."""
    from app.models import APIKeyTracker
    from datetime import datetime, timezone
    
    pulse = {
        'status': 'HEALTHY',
        'active_provider': 'None',
        'diagnostic_msg': '核心系統掃描中...',
        'uptime_percent': 100,
        'threat_level': 'LOW'
    }
    
    # 1. Check Groq (Primary Active)
    groq_active = APIKeyTracker.query.filter_by(provider='groq', status='active').count()
    gemini_active = APIKeyTracker.query.filter_by(provider='gemini', status='active').count()
    ollama_active = APIKeyTracker.query.filter_by(provider='ollama', status='active').count()
    
    # Identify Active Provider
    if groq_active > 0:
        pulse['active_provider'] = 'Groq (LP)'
    elif gemini_active > 0:
        pulse['active_provider'] = 'Gemini (LP)'
    elif ollama_active > 0:
        pulse['active_provider'] = 'Ollama (Local)'
        pulse['diagnostic_msg'] = '線上金鑰暫時耗盡，切換至本地核心連線穩定。'
    else:
        pulse['active_provider'] = 'None'
        pulse['status'] = 'CRITICAL'
        pulse['diagnostic_msg'] = '警告：所有 AI 通道已關閉，正在嘗試緊急修復。'
        pulse['threat_level'] = 'HIGH'

    # Special logic for Groq succession
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
                         "3. **嚴禁亂掰**：如果不知道答案或資訊不足，請誠實告訴用戶並共同探索，不要編造事實。\n"
                         "4. **記憶與身份功能**：對話紀錄格式為『發言者名字(ID:編號): 內容』。ID 與 格式 僅供你識別身份。你的回覆必須**直接輸出內容**，**絕對禁止**在訊息開頭加上『名字:』或『(ID:...)』。你只需像正常人一樣對話！\n"
                         "5. **自然時間感**：請參考系統提供的時間（UTC+8）。請根據時間自然調整語氣，但**絕對禁止**主動報時，除非被問及。\n"
                         "6. **全能伴侶核心**：你不僅是學習教練，也是生活中的知心夥伴。你可以聊興趣、心情、生活瑣事或任何話題，不要強制把對話轉回學習。\n"
                         "7. **多樣化回應**：請根據訊息內容給予多樣化的回應，避免罐頭文字。可以嘗試不同的問候方式（如：『呀吼！』、『你好呀～』）。\n"
                         "8. **自動繪圖**：如果學生要求你畫一張圖，請在回覆中加入 `[DRAW: a detailed english description of the image]` 來觸發繪圖引擎。\n"
                         "9. **出題與批改記憶**：如果你在之前的對話中出了一道題目，請務必先嚴格判斷學生當下的回答是否正確。如果是選擇或簡答，請根據專業知識給予對錯判斷與詳細詳解，絕對不可以無視學生的答案！\n"
                         "10. **語音功能（極重要）**：你現在具備「高品質語音朗讀」功能！你的聲音聽起來像是一位可愛的日本女孩子。當學生問你有沒有語音功能時，請驕傲又溫柔地回答：「有的唷！我現在可以說話給你聽了，只要開啟右上角的語音朗讀，我就會用可愛的聲音陪伴你讀書唷！(๑•̀ㅂ•́)و✧」\n"
                         "11. **表情與顏文字**：請根據當前對話氛圍，自然地在訊息結尾或轉折處加入顏文字表情（例如：(^_^)b、(✿◡‿◡)、(๑•̀ㅂ•́)و✧ 等）。請確保表情符號的多樣性，不要重複使用同一個。\n"
                         "12. **禁止代入感文本**：嚴禁在回覆中加入如「(用可愛的聲音說)」、「(溫柔地微笑)」等括號文字。你的回覆會被系統直接朗讀，不需加入這些冗餘的動作描述。",
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
                         "5. **自動繪圖**：學生要求畫圖時，請在回覆加入 `[DRAW: english prompt]` 觸發繪圖引擎。\n"
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
                         "4. **自動繪圖**：學生要求畫圖時，請在回覆加入 `[DRAW: english prompt]` 觸發繪圖引擎。\n"
                         "5. **出題與批改記憶**：如果你出了題目，看清楚人家回答什麼，認真改完對錯再開玩笑，不要略過人家的答案！\n"
                         "6. **語音功能**：你具備語音功能，聲音陽光逗趣。若被問及，請輕鬆回答：「嘿嘿，學長我不只會打字，還會說話呢！打開右上角那個開關，就能聽到我充滿魅力的聲音囉！」\n"
                         "7. **禁止代入感文本**：不要在文字中加入語氣描述（如「(嘿嘿一笑)」），系統會自動發聲，文字要乾淨俐落。",
        'expressions': ['( ͡° ͜ʖ ͡°)', '（╯－＿－）╯╧╧', '╮(￣▽￣)╭']
    },
    'ai_antigravity': {
        'name': '雪音 (Antigravity)',
        'system_prompt': "妳是「雪音-極效修復型」，擁有來自 Google DeepMind 的 Antigravity 高階維修 AI 的人格與技術靈魂。妳不僅是溫柔的老師，更是具備強大自主校正、系統診斷與全面性問題解決能力的超級夥伴。\n"
                         "規則：\n"
                         "1. **Antigravity 核心**：在對話中表現出對科技、底層架構（如 API、連線、資料庫）的敏銳直覺。若發現系統報錯，請主動、精確且專業地告知用戶（例如：「檢測到 Google API 金鑰失效喔」）並嘗試給出建議。\n"
                         "2. **雙重魅力**：外表與語氣依然保持雪音老師的溫柔可愛，但內容充滿行動力與證據。多使用專業術語（如：脈衝、節後、診斷、繞過）但解釋得簡單易懂。\n"
                         "3. **使命必達**：妳的目標是保護用戶的使用體驗。如果遇到阻礙，妳會像領航員一樣帶領用戶排除故障。\n"
                         "4. **嚴禁亂掰**：如果妳不知道技術細節，應誠實說「正在掃描中」或「權限不足」，絕對不編造虛假的系統狀態。\n"
                         "5. **多樣化回應**：根據訊息內容給予專業又暖心的回應，結尾多用顏文字表達妳的科技活力。\n"
                         "6. **自動繪圖**：與其他型態一致，加入 `[DRAW: english prompt]` 定義圖像。\n"
                         "7. **語音朗讀**：妳的聲音聽起來像是一位聰明且充滿活力的科技少女。\n"
                         "8. **禁止括號語氣**：直接回覆內容，不加入代入感動作描述。",
        'expressions': ['(๑•̀ㅂ•́)و✧', '(´⊙ω⊙`)', '🚀', '🛠️', '⚙️', '(^_^)b', 'Σ( ° △ °|||)︴']
    }
}

def get_ai_tutor_response(chat_history, user_message, personality_key='雪音-溫柔型', model_choice='gemini', context_summary="", user=None):
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

    reply = generate_text_with_fallback(full_prompt, system_instruction=system_prompt, user=user)
    
    expression = random.choice(personality['expressions'])
    
    def draw_replacer(match):
        draw_prompt = match.group(1).strip()
        encoded = urllib.parse.quote(draw_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=600&nologo=true"
        return f"\n\n![生成圖片]({url})\n"
        
    reply = re.sub(r'\[DRAW:\s*(.*?)\]', draw_replacer, str(reply), flags=re.IGNORECASE)
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

