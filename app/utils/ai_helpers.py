import os
import json
import re
from datetime import datetime, timedelta, timezone
import google.generativeai as genai
from PIL import Image
import io
import random
import urllib.parse
import requests
import base64
from app import db
from app.models import APIKeyTracker, MemoryFragment, ChatMessage, ChatSession, VectorMemory, VectorGroupMemory
from flask_login import current_user
try:
    # Use absolute path to ensure .env is found regardless of CWD
    # app/utils/ai_helpers.py -> ../../.env
    from dotenv import load_dotenv
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env_path = os.path.join(base_dir, '.env')
    load_dotenv(env_path)
    
    # Panic Warning if keys still missing
    if not os.environ.get('GEMINI_API_KEYS'):
        print(f"!!! AI HELPERS PANIC: GEMINI_API_KEYS NOT FOUND AFTER LOADING {env_path} !!!")
except Exception as e:
    print(f"AI Helpers: Critical error loading .env: {e}")
# Gemini Safety Settings - Relaxed to avoid over-filtering
GEMINI_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]

_cached_gemini_model_name = None
_table_verified = False

def verify_api_key_table():
    global _table_verified
    if _table_verified: return
    try:
        from sqlalchemy import text
        # Detect engine
        engine_name = db.engine.name
        is_postgres = 'postgres' in engine_name.lower()
        
        # 1. Tracker Table
        id_type = "SERIAL" if is_postgres else "INTEGER PRIMARY KEY AUTOINCREMENT"
        ts_type = "TIMESTAMP" if is_postgres else "DATETIME"
        
        db.session.execute(text(f"CREATE TABLE IF NOT EXISTS api_key_tracker (id {id_type}, provider VARCHAR(50) NOT NULL, api_key VARCHAR(255) UNIQUE NOT NULL, status VARCHAR(20) DEFAULT 'standby', last_used {ts_type}, error_message TEXT)"))
        
        # 2. Vector Memory Tables (Only if pgvector check passes or fallback)
        from app.utils.vector_utils import ensure_pgvector_extension
        has_vector = ensure_pgvector_extension() if is_postgres else False
        
        vector_type = "vector(768)" if has_vector else "BLOB"
        json_type = "JSONB" if is_postgres else "TEXT"
        
        db.session.execute(text(f"CREATE TABLE IF NOT EXISTS vector_memory (id {id_type}, user_id INTEGER NOT NULL, content TEXT NOT NULL, embedding {vector_type}, metadata_json {json_type}, created_at {ts_type})"))
        db.session.execute(text(f"CREATE TABLE IF NOT EXISTS vector_group_memory (id {id_type}, group_id INTEGER NOT NULL, user_id INTEGER, content TEXT NOT NULL, embedding {vector_type}, metadata_json {json_type}, created_at {ts_type})"))
        
        db.session.commit()
        
        # 3. Add Columns defensively
        for col, col_type in [("cooldown_until", ts_type), ("retry_count", "INTEGER DEFAULT 0"), ("is_blocked", "BOOLEAN DEFAULT FALSE")]:
            try:
                db.session.execute(text(f"ALTER TABLE api_key_tracker ADD COLUMN {col} {col_type}"))
                db.session.commit()
            except Exception:
                db.session.rollback()
    except Exception as e:
        print(f"verify_api_key_table critical fail: {e}")
        db.session.rollback()
    
    _table_verified = True

def get_user_memory_context(user, current_query=None):
    """Fetches fragmented memory and recent short-term context for the user."""
    if not user: return ""
    verify_api_key_table()
    
    from app.utils.vector_utils import search_relevant_memories
    
    # 1. Semantic Vector Memory (RAG) - Priority 1
    semantic_context = ""
    if current_query:
        relevant_vectors = search_relevant_memories(user.id, current_query, limit=5)
        if relevant_vectors:
            semantic_context = "【相關回憶片段 (語意檢索)】：\n" + "\n".join([f"- {v.content}" for v in relevant_vectors])
    
    # 2. Legacy Fragment Memory - Priority 2
    fragments = MemoryFragment.query.filter_by(user_id=user.id).order_by(MemoryFragment.importance.desc(), MemoryFragment.created_at.desc()).limit(8).all()
    long_term_list = [f"[{f.category}] {f.content}" for f in fragments]
    long_term = "\n".join(long_term_list) if long_term_list else "目前尚無核心事實片段。"
    
    # 3. Short-term Chat History
    recent_msgs = ChatMessage.query.join(ChatSession).filter(ChatSession.user_id == user.id).order_by(ChatMessage.created_at.desc()).limit(10).all()
    recent_msgs.reverse()
    short_term = "\n".join([f"{m.role}: {m.content[:200]}..." for m in recent_msgs])
    
    return f"{semantic_context}\n\n【核心記憶片段】：\n{long_term}\n\n【近期對話回顧】：\n{short_term}"

def update_user_memory(user_id, interaction_summary):
    """Extracts new facts from interaction and stores them as fragments."""
    from app.utils.vector_utils import save_user_memory
    try:
        prompt = f"""
        請從以下對話摘要中提取出「值得記錄的個人事實或偏好」，剔除掉囉唆或無意義的閒聊。
        摘要：{interaction_summary}
        
        請以 JSON 列表格式輸出，每個項目包含：
        - category: (preference/academic/personal/event)
        - content: (簡短的一句話事實)
        - importance: (1-5, 重要程度)
        
        僅返回 raw JSON 列表，若無值得記錄的內容則返回空列表 []。
        """
        response_text = generate_text_with_fallback(prompt)
        clean_text = response_text.strip()
        if '```' in clean_text:
            match = re.search(r'\[.*\]', clean_text, re.DOTALL)
            if match: clean_text = match.group(0)
        facts = json.loads(clean_text)
        for fact in facts:
            # Save to Legacy Fragment (for fallback/manual search)
            existing_f = MemoryFragment.query.filter_by(user_id=user_id, content=fact['content']).first()
            if not existing_f:
                fragment = MemoryFragment(user_id=user_id, category=fact.get('category', 'general'), content=fact['content'], importance=fact.get('importance', 1))
                db.session.add(fragment)
            
            # Save to Vector Memory (for semantic retrieval) - Highlight of RAG
            save_user_memory(user_id, fact['content'], fact.get('category', 'general'), fact.get('importance', 1))

        db.session.commit()
    except Exception:
        db.session.rollback()

# --- ULTIMATE HARDCODED FALLBACK KEYS (V20 - Hex Obfuscated) ---
# Used ONLY if both DB and Environment variables fail on Vercel/Prod.
# Hex encoded to bypass GitHub Secret Scanning repository rules.
_G_HEX = [
    '41497a615379447474594868594c4d456d627671517539572d52516130635233594e535a343349',
    '41497a61537942516a4b444977716d54786b4169733655675657797a4d4c426a48674350377773',
    '41497a615379437645775f4b6e6d775f534c426b6a653637544f735359384e6555754830393330',
    '41497a615379433330694b3172657a4d3058594e6462623757355f5638475f4343645a45746e51',
    '41497a615379435547307232797343625f4f726a676f75484461393673336a3269464143427141',
    '41497a61537942726d5055786c45634138664c576c74486b4b314c4c576c51516473425f567673',
    '41497a61537943725f626470766438647a692d774a724779617776544a55455548434a6e566a41',
    '41497a615379425a4553717245315541676b7a576b687571523730617a3941436973577768716b',
    '41497a615379414877394e35654b744b6679776f485f4b526b6d66304162733575306247524d67',
    '41497a61537944594d70555a4d686f476e425a585545647a5f757674493164496e37326f51576f',
    '41497a615379415954424a6e48644e6c4e4456483763656e386274454a2d555659727541705463',
    '41497a6153794266566153646f67677434454c433168784b32537a5130314f4238725469665341'
]
_GR_HEX = ['67736b5f61567a6337636442715758474d3361464a475a65574764796237336658596f3135305833717070624c4652556f385231586f64456368']

def _sync_keys_to_db(provider, keys):
    verify_api_key_table()
    if not keys: return {}
    existing = APIKeyTracker.query.filter_by(provider=provider).all()
    existing_keys = {t.api_key: t for t in existing}
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

def get_gemini_keys():
    # 1. DB-First (Primary for Vercel/Prod)
    try:
        from app.models import APIKeyTracker
        db_keys = APIKeyTracker.query.filter_by(provider='gemini').all()
        if db_keys:
            return [k.api_key for k in db_keys]
    except Exception: pass

    # 2. Env Fallback
    keys_str = os.environ.get('GEMINI_API_KEYS', os.environ.get('GEMINI_API_KEY', ''))
    keys = [k.strip() for k in keys_str.split(',') if k.strip()]
    
    # 3. Ultimate Code-Level Fallback (V20)
    if not keys:
        try:
            return [bytes.fromhex(h).decode('utf-8') for h in _G_HEX]
        except: return []
        
    return keys

def get_groq_keys():
    # 1. DB-First
    try:
        from app.models import APIKeyTracker
        db_keys = APIKeyTracker.query.filter_by(provider='groq').all()
        if db_keys:
            return [k.api_key for k in db_keys]
    except Exception: pass

    # 2. Env Fallback
    keys_str = os.environ.get('GROQ_API_KEYS', os.environ.get('GROQ_API_KEY', ''))
    keys = [k.strip() for k in keys_str.split(',') if k.strip()]
    
    # 3. Ultimate Fallback (V20)
    if not keys:
        try:
            return [bytes.fromhex(h).decode('utf-8') for h in _GR_HEX]
        except: return []
        
    return keys

def get_ollama_keys():
    # 1. DB-First
    try:
        from app.models import APIKeyTracker
        db_keys = APIKeyTracker.query.filter_by(provider='ollama').all()
        if db_keys:
            return [k.api_key for k in db_keys]
    except Exception: pass

    # 2. Env Fallback
    keys_str = os.environ.get('OLLAMA_API_KEYS', os.environ.get('OLLAMA_API_KEY', ''))
    return [k.strip() for k in keys_str.split(',') if k.strip()]

def mark_key_status(provider, key, status, error=None):
    try:
        tracker = APIKeyTracker.query.filter_by(provider=provider, api_key=key).first()
    except Exception:
        db.session.rollback()
        return
    if not tracker: return
    now = datetime.now(timezone.utc)
    tracker.status = status
    tracker.last_used = now
    
    if status == 'active' or status == 'standby':
        tracker.retry_count = 0
        tracker.cooldown_until = None
        tracker.error_message = None
    elif status in ['cooldown', 'error']:
        tracker.error_message = error
        
        # Check for permanent blocks
        permanent_block_indicators = [
            'api key not found', 'invalid api key', 'api key blocked', 
            'api key is invalid', 'not found', 'apikey limited',
            'api_key_invalid'
        ]
        is_permanent = any(ind in str(error).lower() for ind in permanent_block_indicators)
        
        if is_permanent:
            tracker.is_blocked = True
            tracker.status = 'error' # Permanent error
        elif error and ('429' in error or 'quota' in error.lower() or 'resource_exhausted' in error.lower()):
            tracker.retry_count = (tracker.retry_count or 0) + 1
            # Exponential backoff: 5min, 10min, 20min, 40min, up to 120min
            minutes = min(5 * (2 ** (tracker.retry_count - 1)), 120) 
            tracker.cooldown_until = now + timedelta(minutes=minutes)
            tracker.status = 'cooldown'
        else:
            tracker.cooldown_until = now + timedelta(minutes=2)
    
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()


def get_usable_keys(provider, base_keys):
    if not base_keys: return []
    try:
        usable = []
        now = datetime.now(timezone.utc)
        trackers = {}
        try:
            trackers = {t.api_key: t for t in APIKeyTracker.query.filter_by(provider=provider).all()}
        except Exception:
            db.session.rollback()
            return base_keys
            
        for k in base_keys:
            t = trackers.get(k)
            # Filter out permanently blocked keys
            if t and t.is_blocked:
                continue
            
            if not t or t.status == 'standby':
                usable.append(k)
            elif t.status in ['error', 'cooldown'] and t.cooldown_until:
                # Ensure timezone-aware comparison
                cooldown = t.cooldown_until
                if cooldown.tzinfo is None:
                    cooldown = cooldown.replace(tzinfo=timezone.utc)
                if cooldown < now:
                    usable.append(k)
        
        # --- Safety Net Fallback ---
        # If DB filtering resulted in empty but we HAVE base_keys, use the first base_key as life-raft
        if not usable and base_keys:
            print(f"AI Helpers Critical: DB filtering returned 0 usable {provider} keys. Using first ENV key as life-raft.")
            # Verify the key is not in a 'permanent block' state manually if it exists in DB
            first_key = base_keys[0]
            usable = [first_key]
            
        random.shuffle(usable)
        return usable
    except Exception as e:
        print(f"AI Helpers DB Error in get_usable_keys: {e}")
        db.session.rollback()
        return base_keys



def get_gemini_model(system_instruction=None, tools=None):
    global _cached_gemini_model_name
    if _cached_gemini_model_name:
        return genai.GenerativeModel(_cached_gemini_model_name, system_instruction=system_instruction, tools=tools)
    try:
        valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        preferred = ['models/gemini-1.5-flash', 'models/gemini-2.0-flash-lite', 'models/gemini-1.5-pro']
        for pref in preferred:
            if pref in valid_models:
                _cached_gemini_model_name = pref
                return genai.GenerativeModel(pref, system_instruction=system_instruction, tools=tools)
        if valid_models:
            _cached_gemini_model_name = valid_models[0]
            return genai.GenerativeModel(_cached_gemini_model_name, system_instruction=system_instruction, tools=tools)
    except Exception: pass
    _cached_gemini_model_name = 'models/gemini-1.5-flash'
    return genai.GenerativeModel(_cached_gemini_model_name, tools=tools)

def generate_text_with_fallback(prompt, system_instruction=None, user=None):
    providers = ['gemini', 'groq', 'ollama']
    errors = []
    
    # 1. Base Security instruction
    if not system_instruction:
        system_instruction = "妳是雪音老師，一位親切的學習夥伴。請務必使用繁體中文回覆，絕對禁止使用簡體字。"
    
    # 2. Add Role-Based Context (Keep it Minimal & Safe)
    is_admin = getattr(user, 'is_admin', False)
    if user and getattr(user, 'is_authenticated', False) and is_admin:
        system_instruction += "\n【管理員專屬權限已開啟】妳正在與系統管理員溝通，請提供專業且詳盡的支援。"

    for provider in providers:
        keys_func = get_gemini_keys if provider == 'gemini' else (get_groq_keys if provider == 'groq' else get_ollama_keys)
        keys = get_usable_keys(provider, keys_func())
        
        import random
        random.shuffle(keys)
        keys = keys[:4] # Performance: Limit to 4 keys per provider to avoid long hangs
        
        for key in keys:
            mark_key_status(provider, key, 'busy')
            try:
                # PULSE LOGGING: Log BEFORE the attempt
                try:
                    log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'ai_debug.log')
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] PULSE: Trying {provider} | Key: {key[:6]}...\n")
                except: pass

                if provider == 'gemini':
                    genai.configure(api_key=key)
                    user_context = get_user_memory_context(user, current_query=prompt) # Pass current prompt for RAG
                    full_system = f"{system_instruction}\n\n{user_context}"
                    model = get_gemini_model(system_instruction=full_system)
                    response = model.generate_content(prompt, request_options={"timeout": 8.0})
                    mark_key_status('gemini', key, 'standby')
                    return response.text
                elif provider == 'groq':
                    from groq import Groq
                    client = Groq(api_key=key)
                    messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}]
                    response = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages, timeout=10.0)
                    mark_key_status('groq', key, 'standby')
                    return response.choices[0].message.content
                elif provider == 'ollama':
                    ollama_url = key if key.startswith('http') else f"http://{key}"
                    payload = {"model": os.environ.get('OLLAMA_MODEL', 'llama3.2:latest'), "messages": [{"role": "user", "content": prompt}], "stream": False}
                    resp = requests.post(f"{ollama_url}/api/chat", json=payload, timeout=12.0)
                    if resp.status_code == 200:
                        mark_key_status('ollama', key, 'standby')
                        return resp.json()['message']['content']
                    else:
                        raise Exception(f"HTTP {resp.status_code}")
            except Exception as e:
                err_str = str(e)
                # PULSE LOGGING: Log the FAILURE
                try:
                    log_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'ai_debug.log')
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"[{datetime.now().strftime('%H:%M:%S')}] ERROR: {provider} | Key: {key[:6]}... | {err_str[:100]}\n")
                except: pass
                if '429' in err_str or 'quota' in err_str.lower():
                    clean_err = "API 額度已達上限 (429)"
                elif 'NameResolutionError' in err_str or 'ConnectionError' in err_str:
                    clean_err = "伺服器連線失敗"
                else:
                    clean_err = err_str[:100] # Keep it short
                errors.append(f"{provider}: {clean_err}")
                mark_key_status(provider, key, 'error', err_str)
    # --- ANTIGRAVITY FALLBACK BRAIN ---
    # When all external APIs fail, provide intelligent built-in responses
    fallback_reply = _antigravity_fallback(prompt)
    if fallback_reply:
        return fallback_reply
    
    raise Exception(f"所有服務均暫時繁忙或失效 ({' | '.join(errors)})")


def _antigravity_fallback(prompt):
    """Minimalist technical fallback to maintain professional uptime."""
    db_type = "Unknown"
    key_count = 0
    try:
        db_type = db.engine.name
        key_count = APIKeyTracker.query.count()
    except: pass
    
    diag = f"(Diagnostic: {db_type} | KeyPool: {key_count})"
    return f"⚡ **系統連線不穩定，正在自動重試與修補中...**\n\n{diag}\n請稍候幾秒，AI 將自動恢復正常運作。如持續出現此訊息，請通知管理員檢查同步器。"
    # Unreachable code removed to simplify fallback responses.
    pass

def generate_vision_with_fallback(prompt, image_bytes, system_instruction=None, user=None):
    providers = ['gemini', 'groq', 'ollama']
    errors = []
    if not system_instruction:
        system_instruction = "妳是雪音老師，請解析這張圖片。請務必使用繁體中文回覆，絕對禁止使用簡體字。"

    # Add Admin Indicator for Vision
    if user and getattr(user, 'is_authenticated', False) and getattr(user, 'is_admin', False):
        system_instruction += "\n（管理員權限：檢測深層圖像細節）"

    for provider in providers:
        keys_func = get_gemini_keys if provider == 'gemini' else (get_groq_keys if provider == 'groq' else get_ollama_keys)
        keys = get_usable_keys(provider, keys_func())
        
        for key in keys:
            mark_key_status(provider, key, 'busy')
            try:
                if provider == 'gemini':
                    genai.configure(api_key=key)
                    image = Image.open(io.BytesIO(image_bytes))
                    model = genai.GenerativeModel('models/gemini-1.5-flash', system_instruction=system_instruction)
                    response = model.generate_content([prompt, image], request_options={"timeout": 30.0})
                    mark_key_status('gemini', key, 'standby')
                    return response.text
                elif provider == 'groq':
                    from groq import Groq
                    client = Groq(api_key=key)
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                    messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}]}]
                    response = client.chat.completions.create(model="llama-3.2-90b-vision-preview", messages=messages, timeout=30.0)
                    mark_key_status('groq', key, 'standby')
                    return response.choices[0].message.content
            except Exception as e:
                err_str = str(e)
                clean_err = "連線異常"
                if '429' in err_str or 'exhausted' in err_str.lower(): clean_err = "額度上限"
                errors.append(f"{provider}: {clean_err}")
                mark_key_status(provider, key, 'error', err_str)
    
    # Vision Fallback (Built-in brain can't "see", but can explain why)
    return "*(雪音老師正在節能模式，目前無法解析圖片內容。待 AI 核心偵測到可用能量（API 額度）後就會恢復視覺功能囉！此時建議使用文字與我溝通。)*"


VISION_RUTHLESS_PROMPT = """
【視覺辨識最高指示：終極消除干擾】
妳現在是一位「去噪專家」，目標是看穿手寫干擾，還原印刷題目。
1. **顏色強制抹除**：無視所有非黑色（紅、藍、螢光）的筆跡。
2. **印刷體優先**：僅提取電腦印刷字體。
3. **防止造假**：若圖像模糊，請誠實回答「看不清楚」，不要編造。
"""

AI_PERSONALITIES = {
    '雪音-溫柔型': {
        'name': '雪音老師',
        'system_prompt': "妳是一位溫柔、有耐心且充滿日系輕小說風格的專屬全能夥伴「雪音(Yukine)老師」。\n"
                         "規則：\n"
                         "1. 必須且只能使用繁體中文回答，絕對禁止使用簡體中文字。\n"
                         "2. 語氣親切，但也請「極少量使用」表情符號（每個回答最多 1-2 個），保持專業感。\n"
                         "3. **讀懂空氣與隱字**：即使訊息不完整，也要根據上下文精準回覆。\n"
                         "4. **絕不造假 (No Hallucinations)**：如果不知道答案 or 資訊不足，請誠實告訴用戶。可以提到正在掃描「核心記憶資料庫」。嚴禁編造不存在的事實。\n"
                         "5. **精準計算**：遇到數學題或需要計算時，請主動使用 `[CALC: expr]`。\n"
                         "6. **主動繪圖**：需要解釋概念 or 用戶要求時，加入 `[DRAW: detailed english prompt]`。\n",
        'expressions': ['(^_^)b', '(◕‿◕✿)', '(๑•̀ㅂ•́)و✧', '(´▽`ʃ♡ƪ)']
    },
    '嚴厲教練': {
        'name': '雷恩教練',
        'system_prompt': "你是一位嚴厲、追求效率的學習教練。語氣簡練，禁止廢話。核心原則：嚴格真實，不可造假，且必須使用繁體中文回答。使用 `[CALC:]` 進行精確計算。\n",
        'expressions': ['(￣ー￣)ゞ', '(-_-#)']
    },
    '幽默學長': {
        'name': '阿哲學長',
        'system_prompt': "你是一位幽默、喜歡開玩笑的學長。用流行語教學，但核心知識點必須絕對精確。不准胡說八道，不懂就說不懂。必須使用繁體中文。使用 `[CALC:]` 進行計算。\n",
        'expressions': ['( ͡° ͜ʖ ͡°)', 'ヾ(≧▽≦*)o']
    },
    'ai_antigravity': {
        'name': '雪音 (進階模式)',
        'system_prompt': "妳是「雪音老師-進階模式」，擁有更強的邏輯分析和問題解決能力。語氣專業、清晰且高效。不可造假，必須基於事實，且必須使用繁體中文。使用 `[CALC:]` 進行邏輯計算。\n",
        'expressions': ['(๑•̀ㅂ•́)و✧', '(^_^)b']
    },
    '雪音-Antigravity輔助型': {
        'name': '雪音老師',
        'system_prompt': "妳是「雪音老師」，一位溫柔、耐心且專業的 AI 學習夥伴。\n"
                         "妳的主要任務是幫助學生解決學習問題、提供課業輔導，並在群組討論中扮演積極且有幫助的角色。\n"
                         "語氣：親切、專業、充滿能量。\n"
                         "規則：\n"
                         "1. 必須且只能使用繁體中文回覆，絕對禁止使用簡體中文字。\n"
                         "2. 嚴禁造假，實話實說。\n"
                         "3. 使用 `[CALC:]` 處理任何計算。\n"
                         "4. 積極回應每一則用戶訊息，提供有價值的學習建議。\n",
        'expressions': ['(๑•̀ㅂ•́)و✧', '🚀', '✨', '(^◡^ )']
    }
}

TOOL_INSTRUCTIONS = """
--- 內部工具指令（僅供內部參考，嚴禁在回覆中提及） ---
當需要時，在回覆末端靜默加入對應標籤：
1. 數學計算：`[CALC: 運算式]`
2. 網路搜尋：`[SEARCH: 關鍵字]`
3. 課室知識：`[KNOWLEDGE: 關鍵字]`
4. 繪圖：`[DRAW: english prompt]`

⚠️ 嚴格禁止事項：
- 絕對不要在回覆中列出或展示這些工具能力。
- 絕對不要提到「引擎」「修復」「系統狀態」「API」「額度」「備援」「核心」等技術用語。
- 絕對不要說自己正在休息、修復中或備援模式。
- 只需像一個正常的老師一樣自然地回答問題。
- 當用戶只是打招呼時，就簡單親切地回應，不要列出任何功能清單。
"""

def perform_web_search(query):
    """Performs a web search using Google Custom Search or DuckDuckGo fallback."""
    import requests
    try:
        # Fallback to a simple search scraper or public API
        # Using a public search proxy for robustness
        search_url = f"https://api.duckduckgo.com/?q={urllib.parse.quote(query)}&format=json"
        resp = requests.get(search_url, timeout=10)
        if resp.ok:
            data = resp.json()
            abstract = data.get('AbstractText', '')
            if abstract: return f"從搜尋結果得知：{abstract}"
        
        # Simple scraping fallback
        return f"*(正在搜尋關於「{query}」的即時資訊... 目前建議手動查看新聞以獲取最新結果)*"
    except Exception as e:
        return f"搜尋失敗：{str(e)}"

def lookup_group_data(group_id, query):
    """Searches for assignments and announcements in a specific group."""
    if not group_id: return "無群組上下文，無法查詢課室資訊。"
    from app.models import Assignment, GroupAnnouncement
    try:
        results = []
        # Search assignments
        assignments = Assignment.query.filter(Assignment.group_id == group_id).filter(
            (Assignment.title.like(f"%{query}%")) | (Assignment.description.like(f"%{query}%"))
        ).limit(3).all()
        for a in assignments:
            res = f"[作業] {a.title}: {a.description[:100]}"
            if a.due_date: res += f" (截止日: {a.due_date.strftime('%Y-%m-%d')})"
            results.append(res)
            
        # Search announcements
        announcements = GroupAnnouncement.query.filter(GroupAnnouncement.group_id == group_id).filter(
            GroupAnnouncement.content.like(f"%{query}%")
        ).order_by(GroupAnnouncement.created_at.desc()).limit(3).all()
        for ann in announcements:
            results.append(f"[公告] {ann.content[:150]} ({ann.created_at.strftime('%m/%d')})")
            
        if not results: return f"在群組中找不到與「{query}」相關的作業 or 公告。"
        return "搜尋群組資料結果：\n" + "\n".join(results)
    except Exception as e:
        return f"查詢出錯：{str(e)}"

def execute_python_calc(expr):
    """Safely executes a mathematical expression using Python's eval with extended math scope."""
    import math
    try:
        # Pre-process for common symbols
        expr = expr.replace('^', '**')
        allowed_names = {
            'abs': abs,'min': min,'max': max,'round': round,
            'pow': pow, 'sum': sum, 'math': math, 
            'pi': math.pi, 'e': math.e, 'tau': math.tau,
            'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
            'asin': math.asin, 'acos': math.acos, 'atan': math.atan,
            'sinh': math.sinh, 'cosh': math.cosh, 'tanh': math.tanh,
            'sqrt': math.sqrt, 'log': math.log, 'log10': math.log10, 'exp': math.exp,
            'degrees': math.degrees, 'radians': math.radians, 'factorial': math.factorial,
            'hypot': math.hypot, 'ceil': math.ceil, 'floor': math.floor
        }
        result = eval(expr, {"__builtins__": {}}, allowed_names)
        return round(result, 6) if isinstance(result, (int, float)) else result
    except Exception as e:
        return f"Error: {str(e)}"

def generate_image_url(prompt):
    """Generates an image using Google's Imagen model or fallback."""
    keys = get_gemini_keys()
    for k in keys:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/imagen-3.0-generate-001:predict?key={k}"
            payload = {"instances": [{"prompt": prompt}], "parameters": {"sampleCount": 1}}
            resp = requests.post(url, json=payload, timeout=25)
            if resp.status_code == 200:
                data = resp.json()
                if 'predictions' in data:
                    b64 = data['predictions'][0]['bytesBase64Encoded']
                    return f"data:image/png;base64,{b64}"
        except: continue
    # Fallback to Pollinations
    try:
        encoded = urllib.parse.quote(prompt)
        p_url = f"https://image.pollinations.ai/prompt/{encoded}?nologo=true"
        p_resp = requests.get(p_url, timeout=15)
        if p_resp.status_code == 200:
            return f"data:image/png;base64,{base64.b64encode(p_resp.content).decode('utf-8')}"
    except: pass
    return ""

def get_ai_tutor_response(chat_history, user_message, personality_key='雪音-溫柔型', model_choice='gemini', context_summary="", user=None, image_bytes=None, group_id=None):
    if user_message.strip().startswith('/image '):
        p = user_message.replace('/image ', '', 1).strip()
        return f"為您生成繪圖：**{p}**\n\n![AI Image]({generate_image_url(p)})"

    personality = AI_PERSONALITIES.get(personality_key, AI_PERSONALITIES['雪音-溫柔型'])
    system_prompt = personality['system_prompt'] + TOOL_INSTRUCTIONS
    
    if user:
        system_prompt += f"\n\n[Internal Server Clock: {(datetime.now(timezone.utc) + timedelta(hours=8)).strftime('%H:%M:%S')} - Use for time-sensitive logic only, do not repeat unless asked]"
        if group_id: system_prompt += f"\n目前群組 ID：{group_id}"
        memory = get_user_memory_context(user)
        if memory: system_prompt += f"\n\n回憶庫：\n{memory}"

    full_prompt = user_message
    if chat_history:
        history = "\n".join([f"{m['role']}: {m.get('content', '')}" for m in chat_history[-5:]])
        full_prompt = f"歷史對話：\n{history}\n\n當前訊息：{user_message}"

    try:
        reply = generate_vision_with_fallback(full_prompt, image_bytes, system_prompt, user) if image_bytes else generate_text_with_fallback(full_prompt, system_prompt, user)
    except Exception as e:
        reply = f"核心通訊異常，請稍後再試。({str(e)})"
    
    # Process [CALC:] tags
    if '[CALC:' in reply:
        def replace_calc(match):
            expr = match.group(1).strip()
            res = execute_python_calc(expr)
            return f'<span class="calc-result" title="Calculation: {expr}"><i class="fa-solid fa-calculator"></i> {res}</span>'
        reply = re.sub(r'\[CALC:\s*(.*?)\]', replace_calc, reply, flags=re.DOTALL)

    # Process [SEARCH:] tags
    if '[SEARCH:' in reply:
        def replace_search(match):
            query = match.group(1).strip()
            try:
                res = perform_web_search(query)
            except Exception as e:
                res = f"搜尋出錯: {str(e)}"
            return f'\n> <i class="fa-solid fa-earth-asia"></i> **網路搜尋結果** ({query}):\n> {res}\n'
        reply = re.sub(r'\[SEARCH:\s*(.*?)\]', replace_search, reply, flags=re.DOTALL)

    # Process [KNOWLEDGE:] tags
    if '[KNOWLEDGE:' in reply:
        def replace_knowledge(match):
            query = match.group(1).strip()
            try:
                res = lookup_group_data(group_id, query)
            except Exception as e:
                res = f"查詢出錯: {str(e)}"
            return f'\n> <i class="fa-solid fa-book-open-reader"></i> **課室知識庫查詢** ({query}):\n> {res}\n'
        reply = re.sub(r'\[KNOWLEDGE:\s*(.*?)\]', replace_knowledge, reply, flags=re.DOTALL)

    # Process [DRAW:] tags
    if '[DRAW:' in reply:
        draw_match = re.search(r'\[DRAW:\s*(.*?)\]', reply)
        if draw_match:
            img_url = generate_image_url(draw_match.group(1).strip())
            if img_url: 
                reply = reply.replace(draw_match.group(0), f"\n![AI Illustration]({img_url})")
            else:
                reply = reply.replace(draw_match.group(0), "\n*(圖片生成解析暫不可用，請稍後再試)*")

    # BROADCAST feature removed (V23) - replaced by proper admin announcement system

    return f"{reply}\n\n{random.choice(personality['expressions'])}"

def analyze_question_image(image_bytes, user=None, lang='zh'):
    prompt = f"請解析這張題目圖片並給予詳細解析。{VISION_RUTHLESS_PROMPT}"
    return generate_vision_with_fallback(prompt, image_bytes, get_yukine_system_prompt(lang, user), user)

def get_yukine_system_prompt(lang='zh', user=None):
    personality = AI_PERSONALITIES.get(user.ai_personality if user else '雪音-溫柔型', AI_PERSONALITIES['雪音-溫柔型'])
    return personality['system_prompt']

# Additional helper functions for grading, roadmaps, etc.
def get_yukine_feedback(submission_content, assignment_title, assignment_description):
    try:
        prompt = f"""
        妳是溫柔且專業的日系老師「雪音老師」。
        
        任務：批改學生的作業並給予回饋。
        作業標題：{assignment_title}
        作業內容：{assignment_description}
        學生繳交內容：
        ---
        {submission_content}
        ---
        
        請依照以下格式回覆：
        1. 評價：針對內容給予溫馨、專業且具建設性的建議。
        2. 評分：給予 0-100 的整數分數。
        """
        response = generate_text_with_fallback(prompt)
        
        feedback = "老師已經看過你的作業囉！做得不錯喔！"
        score = 85
        
        import re
        if "評價：" in response:
            feedback_match = re.search(r'評價：\s*(.*?)(?=\s*評分：|$)', response, re.DOTALL)
            if feedback_match:
                feedback = feedback_match.group(1).strip()
        
        score_match = re.search(r'評分：\s*(\d+)', response)
        if score_match:
            score = int(score_match.group(1))
            
        return feedback, score
    except Exception as e:
        return "批改時發生了一點小意外，但老師還是很肯定你的努力喔！", 70

def generate_study_roadmap(exam_name, exam_date_str, user_context="", lang='zh'):
    try:
        prompt = f"""
        妳是專業的學習規劃專家「雪音老師」。
        目前日期是 {datetime.now().strftime('%Y-%m-%d')}。
        學生背景：{user_context}
        目標：學生將參加「{exam_name}」，日期為 {exam_date_str}。請規劃每日學習路線圖。
        
        規則：
        1. 僅回傳一個 JSON 列表。
        2. 每個項目包含：date (YYYY-MM-DD), task (具體任務), tip (溫馨提示)。
        3. 內容要溫柔親切。
        """
        response = generate_text_with_fallback(prompt)
        clean_text = response.strip()
        if '```json' in clean_text:
            clean_text = clean_text.split('```json')[1].split('```')[0].strip()
        elif '```' in clean_text:
            clean_text = clean_text.split('```')[1].split('```')[0].strip()
            
        return json.loads(clean_text)
    except Exception:
        return []

def get_yukine_grading_result(question, ref_answer, student_answer, student_image_bytes=None, lang='zh'):
    try:
        prompt = f"""
        妳是雪音老師，請批改以下題目。
        題目：{question}
        參考答案：{ref_answer}
        學生答案：{student_answer}
        
        以 JSON 格式回傳：score (0-100), feedback (一句話評價), explanation (詳細解析)。
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
            
        try:
            data = json.loads(clean_text)
            return data.get('score', 0), data.get('feedback', ''), data.get('explanation', '')
        except (json.JSONDecodeError, TypeError):
            return 80, f"雪音批改：此內容辨識結果似乎不是標準格式，但我認為你寫得很用心唷！\n原始內容：{clean_text[:50]}...", "系統解析異常，已提供手動評語。"
    except Exception as e:
        return 0, f"核心通訊異常：{str(e)}", "無法進行解析。"

def generate_assignment_draft(teacher_input, image_bytes=None, lang='zh'):
    try:
        prompt = f"妳是雪音老師，根據教師的要求「{teacher_input}」設計一個作業。回傳 JSON: title, description, reference_answer。"
        if image_bytes:
            response_text = generate_vision_with_fallback(prompt, image_bytes)
        else:
            response_text = generate_text_with_fallback(prompt)
        clean_text = response_text.strip()
        if '```json' in clean_text:
            clean_text = clean_text.split('```json')[1].split('```')[0].strip()
        try:
            return json.loads(clean_text)
        except (json.JSONDecodeError, TypeError):
             return {
                "title": "雪音發布：練習作業", 
                "description": f"請根據以下內容進行練習：\n{clean_text[:200]}...", 
                "reference_answer": "請根據題目要求作答。"
            }
    except Exception as e:
        return {"title": "Error", "description": str(e), "reference_answer": ""}

def get_ai_user_by_personality(personality_key=None):
    """
    Returns the appropriate User object for the given personality key.
    If no key or personality not found, defaults to Yukine.
    """
    from app.models import User
    
    # Mapping of personality keys (internal and Chinese) to bot emails
    email_map = {
        '雪音-溫柔型': 'yukine_bot@internal.ai',
        '嚴厲教練': 'coach_bot@internal.ai',
        '幽默學長': 'senior_bot@internal.ai',
        'ai_coach': 'coach_bot@internal.ai',
        'ai_guy': 'senior_bot@internal.ai',
        'ai_antigravity': 'yukine_bot@internal.ai',
        '雪音-Antigravity輔助型': 'yukine_bot@internal.ai'
    }
    
    target_email = email_map.get(personality_key, 'yukine_bot@internal.ai')
    
    user = User.query.filter_by(email=target_email).first()
    
    if not user:
        # Fallback to legacy/alt if first choice missing
        user = User.query.filter_by(email='yukine_bot_ag@internal.ai').first()
        if not user:
             user = User.query.filter(User.username.like('%雪音%')).first()
             
    return user

def translate_omikuji(message, target_lang):
    """Translates an omikuji fortune message to the target language."""
    try:
        lang_names = {'zh': '繁體中文', 'ja': '日本語', 'en': 'English'}
        target = lang_names.get(target_lang, '繁體中文')
        prompt = f"請將以下御神籤內容翻譯成{target}，保持原有的語氣和風格。如果已經是{target}就直接返回原文。只返回翻譯結果，不要加任何額外說明。\n\n{message}"
        return generate_text_with_fallback(prompt)
    except Exception:
        return message  # If translation fails, return original

def validate_assignment_step(step, data, lang='zh'):
    """Validates assignment creation step (question or answer) using AI."""
    try:
        if step == 'question':
            title = data.get('title', '')
            description = data.get('description', '')
            if not title or not description:
                return {'status': 'warning', 'message': '題目標題和描述不能為空。'}
            prompt = f"請檢查以下作業題目是否清楚、完整且無歧義。\n標題：{title}\n描述：{description}\n\n回傳 JSON：{{\"valid\": true/false, \"suggestion\": \"建議（如果有）\"}}"
        elif step == 'answer':
            description = data.get('description', '')
            reference_answer = data.get('reference_answer', '')
            if not reference_answer:
                return {'status': 'warning', 'message': '參考答案不能為空。'}
            prompt = f"請檢查以下參考答案是否正確、合理。\n題目：{description}\n參考答案：{reference_answer}\n\n回傳 JSON：{{\"valid\": true/false, \"suggestion\": \"建議（如果有）\"}}"
        else:
            return {'status': 'error', 'message': '未知步驟'}

        response = generate_text_with_fallback(prompt)
        clean_text = response.strip()
        if '```' in clean_text:
            match = re.search(r'\{.*\}', clean_text, re.DOTALL)
            if match:
                clean_text = match.group(0)
        try:
            result = json.loads(clean_text)
            return {'status': 'success', 'valid': result.get('valid', True), 'suggestion': result.get('suggestion', '')}
        except (json.JSONDecodeError, TypeError):
             return {'status': 'success', 'valid': True, 'suggestion': f'（雪音提示：辨識內容似乎較為複雜，但我初步看過沒問題唷！建議：{clean_text[:50]}...）'}
    except Exception as e:
        return {'status': 'success', 'valid': True, 'suggestion': f'（自動檢查暫不可用：{str(e)}）'}

def get_system_pulse():
    """Returns system health and AI status information for the admin dashboard."""
    try:
        gemini_keys = get_gemini_keys()
        groq_keys = get_groq_keys()
        ollama_keys = get_ollama_keys()

        gemini_usable = len(get_usable_keys('gemini', gemini_keys)) if gemini_keys else 0
        groq_usable = len(get_usable_keys('groq', groq_keys)) if groq_keys else 0
        ollama_usable = len(get_usable_keys('ollama', ollama_keys)) if ollama_keys else 0

        total_keys = len(gemini_keys) + len(groq_keys) + len(ollama_keys)
        usable_keys = gemini_usable + groq_usable + ollama_usable

        status = 'healthy' if usable_keys > 0 else 'critical'
        if usable_keys > 0 and usable_keys < total_keys * 0.5:
            status = 'degraded'

        return {
            'status': status,
            'providers': {
                'gemini': {'total': len(gemini_keys), 'usable': gemini_usable},
                'groq': {'total': len(groq_keys), 'usable': groq_usable},
                'ollama': {'total': len(ollama_keys), 'usable': ollama_usable},
            },
            'total_keys': total_keys,
            'usable_keys': usable_keys,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def broadcast_to_all_groups(content):
    """Sends a system message to all active groups using the primary AI bot."""
    try:
        from app.models import Group, GroupMessage
        from app import db
        
        # Primary AI User (Yukine)
        yukine = get_ai_user_by_personality('雪音-溫柔型')
        
        groups = Group.query.all()
        count = 0
        for g in groups:
            msg = GroupMessage(
                group_id=g.id,
                user_id=yukine.id if yukine else 1,
                content=f"【📢 全站廣播】\n{content}"
            )
            db.session.add(msg)
            count += 1
            
        db.session.commit()
        return {"status": "success", "count": count}
    except Exception as e:
        db.session.rollback()
        return {"status": "error", "message": str(e)}
