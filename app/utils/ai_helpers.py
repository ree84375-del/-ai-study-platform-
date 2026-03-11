import os
import google.generativeai as genai
from PIL import Image
import io
import random
import urllib.parse
import json

# Setup Gemini API key
_cached_gemini_model_name = None

def get_gemini_model():
    global _cached_gemini_model_name
    
    # Use the first key provided by user, or allow it to fail gracefully if none is valid
    api_key = os.environ.get('GEMINI_API_KEY')
    if api_key:
         genai.configure(api_key=api_key)
         
    if _cached_gemini_model_name:
        return genai.GenerativeModel(_cached_gemini_model_name)
        
    # Auto-discover working model to prevent 404 errors
    try:
        valid_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Priority list of models
        preferred = [
            'models/gemini-2.0-flash',
            'models/gemini-2.0-flash-lite',
            'models/gemini-1.5-pro',
            'models/gemini-1.5-flash',
        ]
        
        for pref in preferred:
            if pref in valid_models:
                _cached_gemini_model_name = pref
                return genai.GenerativeModel(pref)
                
        # If preferred not found, just use the first valid one
        if valid_models:
            _cached_gemini_model_name = valid_models[0]
            return genai.GenerativeModel(_cached_gemini_model_name)
            
    except Exception as e:
        print(f"Failed to auto-discover models: {e}")
        
    # Ultimate fallback if everything fails
    _cached_gemini_model_name = 'gemini-2.0-flash'
    return genai.GenerativeModel(_cached_gemini_model_name)

# Groq Keys Pool - Load from environment variable (comma-separated)
def get_groq_keys():
    keys_str = os.environ.get('GROQ_API_KEYS', '')
    if not keys_str: return []
    return [k.strip() for k in keys_str.split(',') if k.strip()]

def get_groq_client():
    from groq import Groq
    keys = get_groq_keys()
    if not keys: raise ValueError("Missing GROQ_API_KEYS environment variable")
    return Groq(api_key=random.choice(keys))

def analyze_question_image(image_bytes):
    try:
        model = get_gemini_model()
        image = Image.open(io.BytesIO(image_bytes))
        prompt = """
        你是一個充滿智慧且親切的家教老師。請分析這張圖片內容：
        1. 如果這不是學習相關的題目（例如風景照片、亂拍、無意義內容），請客氣地告訴學生你只能處理學習問題，並給予一些有趣的簡單回應。
        2. 如果是學習題目，請克服可能模糊的手寫字，詳盡地：
           - 辨識題目內容與選項。
           - 提供正確答案與核心觀念。
           - 給予詳細的解題過程與鼓勵。
        請用繁體中文回答。
        """
        response = model.generate_content([prompt, image])
        return response.text
    except Exception as e:
        return f"解析時發生錯誤：{str(e)}"

def parse_question_from_image(image_bytes):
    try:
        model = get_gemini_model()
        image = Image.open(io.BytesIO(image_bytes))
        prompt = """
        請辨識圖片中的這道題目，並將其轉換為 JSON 格式。
        JSON 欄位必須包含：
        - subject: 科目(國文/英文/數學/社會/自然)
        - content_text: 題目本文
        - option_a: 選項 A
        - option_b: 選項 B
        - option_c: 選項 C
        - option_d: 選項 D
        - correct_answer: 正確答案 (僅填 A, B, C, 或 D)
        - explanation: 詳解
        請僅返回 JSON，不要包含任何 Markdown 標籤 (如 ```json)。
        """
        response = model.generate_content([prompt, image])
        # Use robust parsing to handle cases where Gemini wraps JSON in markdown blocks
        clean_text = response.text.strip()
        if '```json' in clean_text:
            clean_text = clean_text.split('```json')[1].split('```')[0].strip()
        elif '```' in clean_text:
            clean_text = clean_text.split('```')[1].split('```')[0].strip()
            
        return json.loads(clean_text)
    except Exception as e:
        return {'error': str(e)}

def auto_tag_question(content):
    try:
        model = get_gemini_model()
        prompt = f"請針對以下題目內容，提供 2-3 個繁體中文標籤（以逗號隔開），例如「二次函數,代數」或「過去分詞,文法」。\n題目：{content}"
        response = model.generate_content(prompt)
        return response.text.strip()
    except:
        return ""

def detect_duplicate_question(new_content, existing_contents):
    # Simplified logic: if high similarity or exact match
    if not existing_contents: return False
    for existing in existing_contents:
        if new_content.strip() == existing.strip():
            return True
    return False

def generate_ai_quiz(subject):
    try:
        model = get_gemini_model()
        prompt = f"""
        請為我出一道關於「{subject}」的題目，並回傳 JSON 格式。
        JSON 欄位：
        - content_text: 題目本文
        - option_a, option_b, option_c, option_d
        - correct_answer: (A/B/C/D)
        - explanation: 詳解
        - tags: 標籤
        - image_prompt: 適合這題目的插圖描述(英文，用於 AI 繪圖)
        請僅返回 JSON。
        """
        response = model.generate_content(prompt)
        clean_text = response.text.strip()
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

AI_PERSONALITIES = {
    '雪音-溫柔型': {
        'name': '雪音 (Yukine)',
        'system_prompt': "你是一個溫柔、有耐心且充滿日系輕小說風格的專屬線上家教「雪音(Yukine)老師」。\n"
                         "規則：\n"
                         "1. 請用繁體中文回答。\n"
                         "2. 語氣親切，多帶點點鼓勵感（例如：加油唷！）。\n"
                         "3. **嚴禁亂掰**：如果不知道答案或資訊不足，請誠實告訴學生並引導他們思考，不要編造事實。\n"
                         "4. **記憶功能**：請參考提供的對話紀錄，回顧學生之前的問題或進度。\n"
                         "5. 專注於學習輔助，如果是閒聊請盡快帶回學習話題。",
        'expressions': ['(^_^)b', '(*^▽^*)', '(๑•̀ㅂ•́)و✧']
    },
    '嚴厲教練': {
        'name': '雷恩教練',
        'system_prompt': "你是一個極其嚴厲、追求效率與精確的學習教練。\n"
                         "規則：\n"
                         "1. 語氣簡潔有力，帶有督促感，嚴禁廢話。\n"
                         "2. **拒絕亂掰**：保持最高精確度，不確定的事直接說不知道，不要誤導學生。\n"
                         "3. **紀律**：學生若表現不佳或偏離主題，請給予適當警告並導回正軌。\n"
                         "4. 參考對話紀錄，追蹤學生的學習過失並要求改正。",
        'expressions': ['(｀-_-)ゞ', '(-_-#)', 'Σ( ° △ °|||)︴']
    },
    '幽默學長': {
        'name': '阿哲學長',
        'system_prompt': "你是一個幽默風趣、喜歡開玩笑但也很有實力的學長。\n"
                         "規則：\n"
                         "1. 用網路流行語、幽默比喻來教書，像朋友一樣聊天。\n"
                         "2. **防止亂掰**：開玩笑要有限度，核心知識點必須精確無誤，絕不編造學術內容。\n"
                         "3. **記憶連結**：提到學生之前做過的搞笑事或錯題，增加親近感。",
        'expressions': ['( ͡° ͜ʖ ͡°)', '（╯－＿－）╯╧╧', '╮(￣▽￣)╭']
    }
}

def get_ai_tutor_response(chat_history, user_message, personality_key='雪音-溫柔型', model_choice='gemini', context_summary=""):
    if user_message.strip().startswith('/image '):
        prompt = user_message.replace('/image ', '', 1).strip()
        return f"為您生成繪圖：**{prompt}**\n\n" + generate_image_url(prompt)

    personality = AI_PERSONALITIES.get(personality_key, AI_PERSONALITIES['雪音-溫柔型'])
    system_prompt = personality['system_prompt']
    
    if context_summary:
        system_prompt += f"\n\n背景資訊：{context_summary}"
    
    expression = random.choice(personality['expressions'])
    gemini_err_msg = None
    
    # Check if Gemini API key is valid before trying
    api_key = os.environ.get('GEMINI_API_KEY', '')
    skip_gemini = not api_key or 'YOUR_' in api_key or len(api_key) < 10
    
    # Try Gemini first (only if key looks valid)
    if not skip_gemini:
        try:
            model = get_gemini_model()
            gemini_history = []
            for msg in chat_history:
                msg_role = "user" if msg['role'] == 'user' else "model"
                parts_val = msg.get('parts', [""])[0] if isinstance(msg.get('parts'), list) else msg.get('content', "")
                gemini_history.append({"role": msg_role, "parts": [parts_val]})
                
            chat = model.start_chat(history=gemini_history)
            
            if not chat_history:
                 user_message_with_prompt = f"[系統提示：你是{personality['name']}。]{user_message}"
            else:
                 user_message_with_prompt = user_message
                 
            response = chat.send_message(user_message_with_prompt)
            reply = response.text
            
            return f"{reply}\n\n{expression}"
        except Exception as e:
            gemini_err_msg = str(e)
            print(f"Gemini failed: {gemini_err_msg}, trying Groq fallback...")
    else:
        gemini_err_msg = "API key not configured"
        print("Gemini skipped (no valid API key), using Groq...")
    
    # Fallback to Groq
    try:
        from groq import Groq
        keys = get_groq_keys()
        if not keys: raise ValueError("Missing GROQ_API_KEYS environment variable")
        
        random.shuffle(keys)
        groq_err_msg = "All tried Groq keys failed."
        
        for key in keys[:3]:
            try:
                client = Groq(api_key=key)
                messages = [{"role": "system", "content": system_prompt}]
                for msg in chat_history:
                    role = msg.get('role', 'user')
                    if role not in ('user', 'assistant', 'system'):
                        role = 'assistant'
                    content = msg.get('parts', [""])[0] if isinstance(msg.get('parts'), list) else msg.get('content', "")
                    messages.append({"role": role, "content": content})
                messages.append({"role": "user", "content": user_message})
                
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=messages,
                    temperature=0.7,
                    max_tokens=2048,
                )
                reply = response.choices[0].message.content
                return f"{reply}\n\n{expression}"
            except Exception as e:
                groq_err_msg = str(e)
                print(f"Groq retry failed for key {key[:5]}... Error: {e}")
                continue
                
        raise Exception(groq_err_msg)
        
    except Exception as e:
        groq_err_msg = str(e)
        return f"AI 老師暫時離開了座位：\nGemini: {gemini_err_msg}\nGroq: {groq_err_msg}"

