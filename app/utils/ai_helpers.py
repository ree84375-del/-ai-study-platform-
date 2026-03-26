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
from app.utils.vector_utils import search_relevant_memories, save_user_memory, ensure_pgvector_extension
from flask_login import current_user

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
        # Ensure tables exist
        db.session.execute(text("CREATE TABLE IF NOT EXISTS api_key_tracker (id SERIAL PRIMARY KEY, provider VARCHAR(50) NOT NULL, api_key VARCHAR(255) UNIQUE NOT NULL, status VARCHAR(20) DEFAULT 'standby', last_used TIMESTAMP, error_message TEXT)"))
        db.session.execute(text("CREATE TABLE IF NOT EXISTS user_memory (id SERIAL PRIMARY KEY, user_id INTEGER UNIQUE NOT NULL, memory_content TEXT, last_updated TIMESTAMP)"))
        db.session.execute(text("CREATE TABLE IF NOT EXISTS memory_fragment (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, category VARCHAR(50) DEFAULT 'general', content TEXT NOT NULL, importance INTEGER DEFAULT 1, created_at TIMESTAMP)"))
        
        # Ensure pgvector extension and vector memory tables
        try:
            db.session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            db.session.commit()
            # Vector columns require the extension to be active
            db.session.execute(text("CREATE TABLE IF NOT EXISTS vector_memory (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL, content TEXT NOT NULL, embedding vector(768), metadata_json JSONB, created_at TIMESTAMP)"))
            db.session.execute(text("CREATE TABLE IF NOT EXISTS vector_group_memory (id SERIAL PRIMARY KEY, group_id INTEGER NOT NULL, user_id INTEGER, content TEXT NOT NULL, embedding vector(768), metadata_json JSONB, created_at TIMESTAMP)"))
        except Exception as e:
            logging.error(f"Vector table creation failed: {e}")
            db.session.rollback()

        db.session.commit()
        
        for col, col_type in [("cooldown_until", "TIMESTAMP"), ("retry_count", "INTEGER DEFAULT 0"), ("is_blocked", "BOOLEAN DEFAULT FALSE")]:
            try:
                db.session.execute(text(f"ALTER TABLE api_key_tracker ADD COLUMN {col} {col_type}"))
                db.session.commit()
            except Exception:
                db.session.rollback()
    except Exception:
        db.session.rollback()
    ensure_pgvector_extension() # Attempt to enable pgvector expansion
    _table_verified = True

def get_user_memory_context(user, current_query=None):
    """Fetches fragmented memory and recent short-term context for the user."""
    if not user: return ""
    verify_api_key_table()
    
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
    keys_str = os.environ.get('GEMINI_API_KEYS', os.environ.get('GEMINI_API_KEY', ''))
    return [k.strip() for k in keys_str.split(',') if k.strip()]

def get_groq_keys():
    keys_str = os.environ.get('GROQ_API_KEYS', os.environ.get('GROQ_API_KEY', ''))
    return [k.strip() for k in keys_str.split(',') if k.strip()]

def get_ollama_keys():
    keys_str = os.environ.get('OLLAMA_API_KEYS', os.environ.get('OLLAMA_API_KEY', ''))
    return [k.strip() for k in keys_str.split(',') if k.strip()]

def mark_key_status(provider, key, status, error=None):
    try:
        tracker = APIKeyTracker.query.filter_by(provider=provider, api_key=key).first()
    except Exception:
        db.session.rollback()
        return
    if not tracker: return
    now = datetime.now()
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
            'api key is invalid', 'not found', 'apikey limited'
        ]
        is_permanent = any(ind in str(error).lower() for ind in permanent_block_indicators)
        
        if is_permanent:
            tracker.is_blocked = True
            tracker.status = 'error' # Permanent error
        elif error and ('429' in error or 'quota' in error.lower()):
            tracker.retry_count = (tracker.retry_count or 0) + 1
            # Exponential backoff up to 2 hours
            minutes = min(5 * (2 ** (tracker.retry_count - 1)), 120) 
            tracker.cooldown_until = now + timedelta(minutes=minutes)
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
        now = datetime.now()
        trackers = {}
        try:
            trackers = {t.api_key: t for t in APIKeyTracker.query.filter_by(provider=provider).all()}
        except Exception:
            # If DB is in a failed transaction or table missing, 
            # fall back to using ALL base_keys to ensure AI doesn't stop working.
            db.session.rollback()
            return base_keys
            
        for k in base_keys:
            t = trackers.get(k)
            # Filter out permanently blocked keys
            if t and t.is_blocked:
                continue
                
            if not t or t.status == 'standby' or (t.status in ['error', 'cooldown'] and t.cooldown_until and t.cooldown_until < now):
                usable.append(k)
        random.shuffle(usable)
        return usable if usable else [random.choice(base_keys)]
    except Exception:
        return [random.choice(base_keys)] if base_keys else []

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
        
        for key in keys:
            mark_key_status(provider, key, 'busy')
            try:
                if provider == 'gemini':
                    genai.configure(api_key=key)
                    user_context = get_user_memory_context(user, current_query=prompt) # Pass current prompt for RAG
                    full_system = f"{system_instruction}\n\n{user_context}"
                    model = get_gemini_model(system_instruction=full_system)
                    response = model.generate_content(prompt, request_options={"timeout": 15.0})
                    mark_key_status('gemini', key, 'standby')
                    return response.text
                elif provider == 'groq':
                    from groq import Groq
                    client = Groq(api_key=key)
                    messages = [{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}]
                    response = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=messages, timeout=15.0)
                    mark_key_status('groq', key, 'standby')
                    return response.choices[0].message.content
                elif provider == 'ollama':
                    ollama_url = key if key.startswith('http') else f"http://{key}"
                    payload = {"model": os.environ.get('OLLAMA_MODEL', 'llama3.2:latest'), "messages": [{"role": "user", "content": prompt}], "stream": False}
                    resp = requests.post(f"{ollama_url}/api/chat", json=payload, timeout=20.0)
                    if resp.status_code == 200:
                        mark_key_status('ollama', key, 'standby')
                        return resp.json()['message']['content']
                    else:
                        raise Exception(f"HTTP {resp.status_code}")
            except Exception as e:
                err_str = str(e)
                if '429' in err_str or 'quota' in err_str.lower():
                    clean_err = "API 額度已達上限 (429)"
                elif 'NameResolutionError' in err_str or 'ConnectionError' in err_str:
                    clean_err = "伺服器連線失敗"
                else:
                    clean_err = err_str[:100] # Keep it short
                errors.append(f"{provider}: {clean_err}")
                mark_key_status(provider, key, 'error', err_str)
    
    raise Exception(f"所有服務均暫時繁忙或失效 ({' | '.join(errors)})")

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
                if '429' in err_str: clean_err = "額度上限"
                errors.append(f"{provider}: {clean_err}")
                mark_key_status(provider, key, 'error', err_str)
    raise Exception(f"視覺 AI 繁忙中 ({' | '.join(errors)})")

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
    }
}

TOOL_INSTRUCTIONS = """
--- 核心核心指令：工具包使用指南 ---
妳擁有以下外部能力，請根據用戶需求，在回覆中加入對應標籤：
1. 數學計算：當遇到算術、方程式或科學計算時，請輸出 `[CALC: 運算式]`。
2. 網路搜尋：當用戶詢問「即時訊息」、「新聞」或妳不確定的事實時，請輸出 `[SEARCH: 搜尋關鍵字]`。
3. 課室知識：當用戶詢問「群組作業」、「公告」或「課程內容」時，請輸出 `[KNOWLEDGE: 關鍵字]`。
4. 繪圖：當用戶要求圖片或需要視覺解釋時，輸出 `[DRAW:Detailed English Prompt]`。

規則：每個標籤必須獨自一行或位於回覆末端。妳一次只能執行一個標籤。
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
            
        if not results: return f"在群組中找不到與「{query}」相關的作業或公告。"
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
    admin_instructions = ""
    try:
        if current_user.is_authenticated and current_user.is_admin:
            admin_instructions = "\n\n【管理員專屬權限】\n身為管理員助理，妳擁有一項特殊能力：`[BROADCAST: 訊息內容]`。當管理員（甚至是目前的對話對象）要求妳向所有人廣播訊息時，請使用此標籤。例如：`[BROADCAST: 大家好，系統維護將於一小時後開始。]`\n使用此標籤後，訊息會立即同步至全站所有群組。"
    except: pass
    
    system_prompt = personality['system_prompt'] + TOOL_INSTRUCTIONS + admin_instructions
    
    if user:
        system_prompt += f"\n\n現在時間：{(datetime.now(timezone.utc) + timedelta(hours=8)).strftime('%Y-%m-%d %H:%M:%S')}"
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

    # Process [BROADCAST:] tags (Admin Only)
    if '[BROADCAST:' in reply:
        def replace_broadcast(match):
            content = match.group(1).strip()
            try:
                # Security double-check
                if current_user.is_authenticated and current_user.is_admin:
                    res = broadcast_to_all_groups(content)
                    if res.get('status') == 'success':
                        return f'\n> <i class="fa-solid fa-tower-broadcast"></i> **系統廣播已發出** (至 {res["count"]} 個群組)\n> 內容：{content}\n'
                    else:
                        return f'\n> <i class="fa-solid fa-triangle-exclamation"></i> **廣播失敗**: {res.get("message")}\n'
                else:
                    return '\n> <i class="fa-solid fa-lock"></i> **權限不足**: 僅管理員可執行廣播作業。\n'
            except Exception as e:
                return f'\n> 廣播出錯: {str(e)}\n'
        reply = re.sub(r'\[BROADCAST:\s*(.*?)\]', replace_broadcast, reply, flags=re.DOTALL)

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
            
        data = json.loads(clean_text)
        return data.get('score', 0), data.get('feedback', ''), data.get('explanation', '')
    except Exception:
        return 0, "批改出錯了，請老師手動檢查喔！", "錯誤原因：系統暫時無法解析。"

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
        return json.loads(clean_text)
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
