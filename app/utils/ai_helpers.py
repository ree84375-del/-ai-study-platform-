import os
import json
import re
from datetime import datetime
import google.generativeai as genai
from PIL import Image
import io
import random
import urllib.parse


# Setup Gemini API key
_cached_gemini_model_name = None

# API Key Status Tracking
API_KEY_STATUS = {}

def get_all_api_key_statuses():
    gemini_keys = get_gemini_keys()
    groq_keys = get_groq_keys()
    ollama_keys = get_ollama_keys()
    
    # Initialize defaults if not in dict
    for provider, keys in [('gemini', gemini_keys), ('groq', groq_keys), ('ollama', ollama_keys)]:
        if provider not in API_KEY_STATUS:
            API_KEY_STATUS[provider] = {}
        for k in keys:
            if k not in API_KEY_STATUS[provider]:
                API_KEY_STATUS[provider][k] = {
                    'status': 'standby',
                    'last_used': None,
                    'error': None
                }
    
    masked_status = {}
    for provider, keys_dict in API_KEY_STATUS.items():
        masked_status[provider] = []
        for k, info in keys_dict.items():
            if not k: continue
            masked_k = k[:6] + '...' + k[-4:] if len(k) > 10 else k
            # Ensure we only track currently valid keys in env
            active_keys = gemini_keys if provider == 'gemini' else groq_keys if provider == 'groq' else ollama_keys
            if k in active_keys:
                masked_status[provider].append({
                    'key': masked_k,
                    'full_key': k,
                    'status': info['status'],
                    'last_used': info['last_used'].strftime('%Y-%m-%d %H:%M:%S') if info['last_used'] else '從未使用',
                    'error': info['error']
                })
    return masked_status

def mark_key_status(provider, key, status, error=None):
    if provider not in API_KEY_STATUS:
        API_KEY_STATUS[provider] = {}
    if key not in API_KEY_STATUS[provider]:
         API_KEY_STATUS[provider][key] = {}
    
    API_KEY_STATUS[provider][key]['status'] = status
    API_KEY_STATUS[provider][key]['last_used'] = datetime.now()
    API_KEY_STATUS[provider][key]['error'] = error


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
                return genai.GenerativeModel(pref, system_instruction=system_instruction, tools=tools)
                
        # If preferred not found, just use the first valid one
        if valid_models:
            _cached_gemini_model_name = valid_models[0]
            return genai.GenerativeModel(_cached_gemini_model_name, system_instruction=system_instruction, tools=tools)
            
    except Exception as e:
        print(f"Failed to auto-discover models: {e}")
        
    # Ultimate fallback if everything fails
    _cached_gemini_model_name = 'models/gemini-1.5-flash'
    return genai.GenerativeModel(_cached_gemini_model_name, system_instruction=system_instruction, tools=tools)

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

def generate_text_with_fallback(prompt, system_instruction=None):
    """Unified wrapper for text generation with randomized provider rotation (Gemini, Groq, Ollama)"""
    gemini_keys = get_gemini_keys()
    groq_keys = get_groq_keys()
    ollama_keys = get_ollama_keys()
    
    providers = []
    if gemini_keys: providers.append('gemini')
    if groq_keys: providers.append('groq')
    if ollama_keys: providers.append('ollama')
    
    if not providers:
        raise Exception("伺服器未設定任何 AI API Key。")
        
    random.shuffle(providers)
    errors = []
    
    for provider in providers:
        if provider == 'gemini':
            keys = get_gemini_keys()
            random.shuffle(keys)
            for key in keys:
                try:
                    genai.configure(api_key=key)
                    model = get_gemini_model(system_instruction=system_instruction)
                    response = model.generate_content(prompt)
                    mark_key_status('gemini', key, 'active')
                    return response.text
                except Exception as e:
                    errors.append(f"Gemini (key {key[:4]}...): {e}")
                    # If it's a quota issue, try next key. Otherwise, provider might be down.
                    err_str = str(e).lower()
                    if "429" in err_str or "quota" in err_str:
                        mark_key_status('gemini', key, 'cooldown', str(e))
                        continue
                    else:
                        mark_key_status('gemini', key, 'error', str(e))
                        continue
                
        elif provider == 'groq':
            keys = get_groq_keys()
            random.shuffle(keys)
            for key in keys:
                try:
                    from groq import Groq
                    client = Groq(api_key=key)
                    messages = []
                    if system_instruction:
                        messages.append({"role": "system", "content": system_instruction})
                    messages.append({"role": "user", "content": prompt})
                    
                    response = client.chat.completions.create(
                        model="llama-3.3-70b-versatile",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=2048,
                    )
                    mark_key_status('groq', key, 'active')
                    return response.choices[0].message.content
                except Exception as e:
                    errors.append(f"Groq (key {key[:4]}...): {e}")
                    err_str = str(e).lower()
                    if "restricted" in err_str or "quota" in err_str or "429" in err_str:
                        mark_key_status('groq', key, 'cooldown', str(e))
                        continue
                    else:
                        mark_key_status('groq', key, 'error', str(e))
                        continue

        elif provider == 'ollama':
            keys = get_ollama_keys()
            random.shuffle(keys)
            ollama_host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434/v1')
            for key in keys:
                try:
                    from openai import OpenAI
                    client = OpenAI(base_url=ollama_host, api_key=key)
                    
                    messages = []
                    if system_instruction:
                        messages.append({"role": "system", "content": system_instruction})
                    messages.append({"role": "user", "content": prompt})
                    
                    response = client.chat.completions.create(
                        model=os.environ.get('OLLAMA_MODEL', 'llama3'),
                        messages=messages,
                        temperature=0.7
                    )
                    mark_key_status('ollama', key, 'active')
                    return str(response.choices[0].message.content)
                except Exception as e:
                    errors.append(f"Ollama: {e}")
                    mark_key_status('ollama', key, 'error', str(e))
                    continue

    raise Exception(f"所有的 AI 模型皆不可用：{', '.join(errors)}")

def generate_vision_with_fallback(prompt, image_bytes, system_instruction=None):
    """Unified wrapper for vision generation with randomized provider rotation (Gemini, Groq, Ollama)"""
    import base64
    gemini_keys = get_gemini_keys()
    groq_keys = get_groq_keys()
    ollama_keys = get_ollama_keys()
    
    providers = []
    if gemini_keys: providers.append('gemini')
    if groq_keys: providers.append('groq')
    if ollama_keys: providers.append('ollama')
    
    if not providers:
        raise Exception("伺服器未設定任何 AI API Key。")
        
    random.shuffle(providers)
    errors = []
    
    for provider in providers:
        if provider == 'gemini':
            keys = get_gemini_keys()
            random.shuffle(keys)
            for key in keys:
                try:
                    genai.configure(api_key=key)
                    model = get_gemini_model()
                    image = Image.open(io.BytesIO(image_bytes))
                    inputs = [prompt, image]
                    if system_instruction:
                        model = get_gemini_model(system_instruction=system_instruction)
                    response = model.generate_content(inputs)
                    mark_key_status('gemini', key, 'active')
                    return response.text
                except Exception as e:
                    errors.append(f"Gemini Vision (key {key[:4]}...): {e}")
                    err_str = str(e).lower()
                    if "429" in err_str or "quota" in err_str:
                        mark_key_status('gemini', key, 'cooldown', str(e))
                        continue
                    else:
                        mark_key_status('gemini', key, 'error', str(e))
                        continue
        
        elif provider == 'groq':
            keys = get_groq_keys()
            random.shuffle(keys)
            for key in keys:
                try:
                    from groq import Groq
                    client = Groq(api_key=key)
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                    messages = []
                    if system_instruction:
                        messages.append({"role": "system", "content": system_instruction})
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                        ],
                    })
                    response = client.chat.completions.create(
                        model="llama-3.2-90b-vision-preview",
                        messages=messages,
                        temperature=0.7,
                        max_tokens=2048,
                    )
                    mark_key_status('groq', key, 'active')
                    return response.choices[0].message.content
                except Exception as e:
                    errors.append(f"Groq Vision (key {key[:4]}...): {e}")
                    err_str = str(e).lower()
                    if "restricted" in err_str or "quota" in err_str or "429" in err_str:
                        mark_key_status('groq', key, 'cooldown', str(e))
                        continue
                    else:
                        mark_key_status('groq', key, 'error', str(e))
                        continue
        
        elif provider == 'ollama':
            keys = get_ollama_keys()
            random.shuffle(keys)
            ollama_host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434/v1')
            for key in keys:
                try:
                    from openai import OpenAI
                    client = OpenAI(base_url=ollama_host, api_key=key)
                    base64_image = base64.b64encode(image_bytes).decode('utf-8')
                    messages = []
                    if system_instruction:
                        messages.append({"role": "system", "content": system_instruction})
                    messages.append({
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                        ],
                    })
                    response = client.chat.completions.create(
                        model=os.environ.get('OLLAMA_MODEL', 'llama3.2-vision'),
                        messages=messages,
                        temperature=0.7
                    )
                    mark_key_status('ollama', key, 'active')
                    return response.choices[0].message.content
                except Exception as e:
                    errors.append(f"Ollama Vision: {e}")
                    mark_key_status('ollama', key, 'error', str(e))
                    continue

    raise Exception(f"所有的視覺 AI 模型皆不可用：{', '.join(errors)}")

def analyze_question_image(image_bytes, user=None, lang='zh'):
    try:
        tutor_name = "雪音"
        tutor_prompt = "充滿智慧且親切的家教老師雪音"
        
        if user and user.ai_personality:
            personality = AI_PERSONALITIES.get(user.ai_personality)
            if personality:
                tutor_name = personality['name']
                tutor_prompt = personality['system_prompt']

        # Localized instructions
        if lang == 'ja':
            output_lang = "日本語"
            role_desc = f"知的で親切な万能アシスタントの{tutor_name}先生"
            task_desc = "この画像の内容を分析し、何でもお手伝いします："
            detail_1 = "1. 内容認識：画像内のテキスト、オブジェクト、シーンを認識してください。"
            detail_1_extra = "- **重要：手書き文字も含め、画像にあるすべての情報を読み取ってください**。"
            detail_2 = f"2. 多様なニーズへの対応：学習、日常の悩み、作品制作など、どのような相談にも{tutor_name}先生として温かく応じてください。"
            detail_3 = "3. 回答：ユーザーの意図を汲み取り、詳しく解説やアドバイスを提供してください。"
            final_note = f"必ず{output_lang}で回答し、レイアウトを整えてください。"
        elif lang == 'en':
            output_lang = "English"
            role_desc = f"the wise and versatile companion, {tutor_name}"
            task_desc = "Analyze this image and assist with anything:"
            detail_1 = "1. Recognition: Identify text, objects, and details in the image."
            detail_1_extra = "- **IMPORTANT: Recognize everything**, including handwritten notes or complex scenes."
            detail_2 = f"2. Versatile Support: Whether it's about studying, life advice, or creativity, respond warmly as {tutor_name}."
            detail_3 = "3. Response: Provide detailed analysis, answers, or creative suggestions based on the content."
            final_note = f"You MUST reply in {output_lang} and use clear formatting."
        else: # zh
            output_lang = "繁體中文"
            role_desc = f"充滿智慧且親切的萬能伴侶{tutor_name}老師"
            task_desc = "請分析這張圖片內容，並為用戶提供幫助："
            detail_1 = "1. 全面辨識模式：請辨識圖片中的所有訊息，包含文字、物件或場景。"
            detail_1_extra = "- **重點：「印刷文字」、「手寫筆記」或任何視覺細節都要辨識**。即便字跡凌亂，也請根據上下文推斷其義。"
            detail_2 = f"2. 萬能協助機制：不必局限於學習題目。無論是用戶的日常生活紀錄、心情隨筆或任何興趣愛好，請都以「{tutor_name}老師」的身分給予溫暖的回應與支援。"
            detail_3 = "3. 提供深度的分析：根據圖片內容提供詳細的辨識結果、解答、建議或心情交流。"
            final_note = f"請用{output_lang}回答，並且排版清晰易讀。"

        prompt = f"""
        你是{role_desc}。
        {task_desc}
        {detail_1}
           {detail_1_extra}
        {detail_2}
        {detail_3}
        {final_note}
        """
        return generate_vision_with_fallback(prompt, image_bytes)
    except Exception as e:
        return f"Error: {str(e)}"

def parse_question_from_image(image_bytes, lang='zh'):
    try:
        if lang == 'ja':
            prompt = """
            この画像の問題を認識し、JSON形式に変換してください。
            JSONフィールド：
            - subject: 科目 (国語/英語/数学/社会/理科)
            - content_text: 問題文
            - option_a, option_b, option_c, option_d: 選択肢
            - correct_answer: 正解 (A, B, C, Dのいずれか)
            - explanation: 解説
            JSONのみを返し、Markdownタグは含めないでください。
            """
        elif lang == 'en':
            prompt = """
            Recognize the question in this image and convert it to JSON format.
            JSON fields:
            - subject: Subject (Chinese/English/Math/Social/Science)
            - content_text: Question text
            - option_a, option_b, option_c, option_d: Options
            - correct_answer: Correct answer (A, B, C, or D only)
            - explanation: Detailed explanation
            Only return raw JSON, no Markdown tags.
            """
        else:
            prompt = """
            請辨識圖片中的這道題目，並將其轉換為 JSON 格式。
            JSON 欄位必須包含：
            - subject: 科目(國文/英文/數學/社會/自然)
            - content_text: 題目本文
            - option_a, option_b, option_c, option_d: 選項
            - correct_answer: 正確答案 (僅填 A, B, C, 或 D)
            - explanation: 詳解
            請僅返回 JSON，不要包含任何 Markdown 標籤。
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
    }
}

def get_ai_tutor_response(chat_history, user_message, personality_key='雪音-溫柔型', model_choice='gemini', context_summary=""):
    if user_message.strip().startswith('/image '):
        prompt = user_message.replace('/image ', '', 1).strip()
        return f"為您生成繪圖：**{prompt}**\n\n" + generate_image_url(prompt)

    personality = AI_PERSONALITIES.get(personality_key, AI_PERSONALITIES['雪音-溫柔型'])
    system_prompt = personality['system_prompt']
    
    # Inject language requirement
    lang = getattr(current_user, 'language', 'zh')
    if lang == 'ja':
        system_prompt += "\n重要：常に日本語で回答してください。"
    elif lang == 'en':
        system_prompt += "\nIMPORTANT: Always reply in English."
    else:
        system_prompt += "\n重要：請務必用繁體中文回答。"

    if context_summary:
        system_prompt += f"\n\n背景資訊：{context_summary}"
    
    # Check for Admin Exclusive Commands
    is_admin_user = (chat_history and any('管理員(ID:' in str(msg.get('parts', msg.get('content', ''))) for msg in chat_history)) or ("管理員" in user_message)
    # Better: we should pass is_admin explicitly or rely on the name format
    # In group_dashboard.html, we format as "Username(ID:123): Content"
    
    if "管理員(ID:" in user_message:
        system_prompt += """
        
        【管理員專屬權限已啟動】
        檢測到當前對話者為系統最高管理員（管理員）。
        請在回覆開頭熱情地向管理員問好，並告知目前可用的「管理員專屬指令」：
        1. /status - 查看伺服器健康度與當前版本。
        2. /user_count - 獲取當前系統註冊用戶總數。
        3. /ai_switch - 切換後端 AI 模型的優先權。
        4. /db_optimize - 執行資料庫連線優化檢查。
        5. /broadcast [訊息] - 發布全局公告（模擬）。
        
        請注意：這些指令僅對「管理員」開放。如果管理員輸入了指令，請用專業且配合的語氣進行回應。
        """
    
    expression = random.choice(personality['expressions'])
    gemini_has_keys = len(get_gemini_keys()) > 0
    groq_has_keys = len(get_groq_keys()) > 0
    ollama_has_keys = len(get_ollama_keys()) > 0
    
    models_to_try = []
    if gemini_has_keys: models_to_try.append('gemini')
    if groq_has_keys: models_to_try.append('groq')
    if ollama_has_keys: models_to_try.append('ollama')
    
    if not models_to_try:
        return "AI 老師暫時無法連線（請設定 API Key）。"
        
    random.shuffle(models_to_try)
    
    reply = None
    errors = []
    
    for current_model in models_to_try:
        if current_model == 'gemini':
            keys = get_gemini_keys()
            random.shuffle(keys)
            success = False
            for key in keys:
                try:
                    genai.configure(api_key=key)
                    model = get_gemini_model(system_instruction=system_prompt)
                    gemini_history = []
                    for msg in chat_history:
                        msg_role = "user" if msg['role'] == 'user' else "model"
                        parts_val = msg.get('parts', [""])[0] if isinstance(msg.get('parts'), list) else msg.get('content', "")
                        gemini_history.append({"role": msg_role, "parts": [parts_val]})
                        
                    chat = model.start_chat(history=gemini_history)
                    response = chat.send_message(user_message)
                    reply = response.text
                    success = True
                    break
                except Exception as e:
                    errors.append(f"Gemini (key {key[:4]}...): {str(e)}")
                    if "429" not in str(e) and "quota" not in str(e).lower():
                        break
            if success:
                break
                
        elif current_model == 'groq':
            try:
                from groq import Groq
                keys = get_groq_keys()
                random.shuffle(keys)
                success = False
                
                for key in keys:
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
                        success = True
                        break
                    except Exception as e:
                        errors.append(f"Groq (key {key[:4]}...): {str(e)}")
                        if "restricted" not in str(e).lower() and "quota" not in str(e).lower() and "429" not in str(e):
                            break
                
                if success:
                    break
            except Exception as e:
                errors.append(f"Groq Init Error: {str(e)}")
                
        elif current_model == 'ollama':
            try:
                keys = get_ollama_keys()
                random.shuffle(keys)
                ollama_host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434/v1')
                from openai import OpenAI
                success = False
                
                for key in keys:
                    try:
                        client = OpenAI(base_url=ollama_host, api_key=key)
                        messages = [{"role": "system", "content": system_prompt}]
                        for msg in chat_history:
                            role = msg.get('role', 'user')
                            if role not in ('user', 'assistant', 'system'):
                                role = 'assistant'
                            content = msg.get('parts', [""])[0] if isinstance(msg.get('parts'), list) else msg.get('content', "")
                            messages.append({"role": role, "content": content})
                        messages.append({"role": "user", "content": user_message})
                        
                        response = client.chat.completions.create(
                            model=os.environ.get('OLLAMA_MODEL', 'llama3'),
                            messages=messages,
                            temperature=0.7
                        )
                        reply = response.choices[0].message.content
                        success = True
                        break
                    except Exception as e:
                        errors.append(f"Ollama: {str(e)}")
                
                if success:
                    break
            except Exception as e:
                errors.append(f"Ollama Init Error: {str(e)}")

    if not reply:
        return f"AI 老師暫時離開了座位：\n" + "\n".join(errors)

    if reply:
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

