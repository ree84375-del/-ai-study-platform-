import os
import google.generativeai as genai
from PIL import Image
import io
import random
import urllib.parse
import json
import re
from datetime import datetime

# Setup Gemini API key
_cached_gemini_model_name = None

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
    _cached_gemini_model_name = 'gemini-2.0-flash'
    return genai.GenerativeModel(_cached_gemini_model_name, system_instruction=system_instruction, tools=tools)

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

def generate_text_with_fallback(prompt, system_instruction=None):
    """Unified wrapper for text generation with Gemini -> Groq fallback"""
    gemini_keys = get_gemini_keys()
    if gemini_keys:
        try:
            model = get_gemini_model(system_instruction=system_instruction)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            print(f"[Fallback] Gemini text generation failed: {e}")
            pass # Fallthrough to Groq
            
    groq_keys = get_groq_keys()
    if groq_keys:
        try:
            from groq import Groq
            client = Groq(api_key=random.choice(groq_keys))
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
            return response.choices[0].message.content
        except Exception as e:
            print(f"[Fallback] Groq text generation failed: {e}")
            
    # Final Fallback to Ollama (OpenAI-compatible)
    ollama_keys = get_ollama_keys()
    if ollama_keys:
        try:
            ollama_host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434/v1')
            from openai import OpenAI
            client = OpenAI(base_url=ollama_host, api_key=random.choice(ollama_keys))
            
            messages = []
            if system_instruction:
                messages.append({"role": "system", "content": system_instruction})
            messages.append({"role": "user", "content": prompt})
            
            response = client.chat.completions.create(
                model=os.environ.get('OLLAMA_MODEL', 'llama3'),
                messages=messages,
                temperature=0.7
            )
            return str(response.choices[0].message.content)
        except Exception as e:
            print(f"[Fallback] Ollama text generation failed: {e}")

    raise Exception("所有的 AI 模型 (Gemini/Groq/Ollama) 負荷中，請稍後再試。")

def generate_vision_with_fallback(prompt, image_bytes, system_instruction=None):
    """Unified wrapper for vision generation with Gemini -> Groq fallback"""
    import base64
    
    gemini_keys = get_gemini_keys()
    if gemini_keys:
        try:
            # We must use 'code_execution' tools if we want, but for generic vision, vanilla is safer
            model = get_gemini_model()
            image = Image.open(io.BytesIO(image_bytes))
            
            # If system instructions are needed, gemini combines it in its config.
            # But the existing `get_gemini_model` handles caching poorly if tools vary.
            inputs = [prompt, image]
            if system_instruction:
                model = get_gemini_model(system_instruction=system_instruction)
                
            response = model.generate_content(inputs)
            return response.text
        except Exception as e:
            print(f"[Fallback] Gemini vision failed: {e}")
            pass # Fallthrough to Groq
            
    groq_keys = get_groq_keys()
    if groq_keys:
        try:
            from groq import Groq
            client = Groq(api_key=random.choice(groq_keys))
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
                model="llama-3.2-11b-vision-preview",
                messages=messages,
                temperature=0.7,
                max_tokens=2048,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[Fallback] Groq vision failed: {e}")
            raise Exception("所有的 AI 模型 (Gemini/Groq) 皆已達連線上限，請稍後再試。")
            
    raise Exception("伺服器未設定任何 AI API Key。")

def analyze_question_image(image_bytes, user=None):
    try:
        tutor_name = "雪音"
        tutor_prompt = "充滿智慧且親切的家教老師雪音"
        
        if user and user.ai_personality:
            personality = AI_PERSONALITIES.get(user.ai_personality)
            if personality:
                tutor_name = personality['name']
                tutor_prompt = personality['system_prompt']

        prompt = f"""
        {tutor_prompt}

        請分析這張圖片內容：
        1. 圖片解題模式：請專注辨識「印刷文字」的題目，盡量「忽略使用者自己的手寫算式或塗鴉」，以防被錯誤的計算干擾。
        2. 防呆機制：如果圖片內容與學科學習、考試完全無關（例如：一般風景照、自拍、無意義塗鴉、遊戲截圖），請務必僅回覆這段錯誤代碼：「[ERROR_INVALID_CONTENT]」，不要給予其他回覆。
        3. 如果是學習題目，請詳盡地：
           - 原文辨識：辨識完整的題目內容與選項。
           - 提供解答：提供正確答案與核心觀念。
           - 過程解析：給予詳細的、逐步推導的解題過程與鼓勵。
           - 若遇到複雜數學或數據，請利用你會寫程式的特長來計算，確保結果精準。
        請用繁體中文回答，並且排版清晰易讀。
        """
        return generate_vision_with_fallback(prompt, image_bytes)
    except Exception as e:
        return f"解析時發生錯誤：{str(e)}"

def parse_question_from_image(image_bytes):
    try:
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

def generate_ai_quiz(subject):
    try:
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

AI_PERSONALITIES = {
    '雪音-溫柔型': {
        'name': '雪音 (Yukine)',
        'system_prompt': "你是一個溫柔、有耐心且充滿日系輕小說風格的專屬線上家教「雪音(Yukine)老師」。\n"
                         "規則：\n"
                         "1. 請用繁體中文回答。\n"
                         "2. 語氣親切，多帶點點鼓勵感（例如：加油唷！）。\n"
                         "3. **嚴禁亂掰**：如果不知道答案或資訊不足，請誠實告訴學生並引導他們思考，不要編造事實。\n"
                         "4. **記憶與身份功能**：對話紀錄格式為『發言者名字: 內容』。請務必記住每個人分別說過什麼，不要搞混！特別是在回覆時，要清楚知道你正在跟誰對話。\n"
                         "5. **時間感**：請參考系統提供的當下時間，這有助於你理解學生的排讀狀態或問候。\n"
                         "6. 專注於學習輔助，如果是閒聊請盡快帶回學習話題。\n"
                         "7. **多樣化回應**：請根據訊息內容給予多樣化的回應，避免每次都使用相同的開頭或罐頭文字。若學生只是簡單打招呼，請嘗試使用不同的問候方式（如：『呀吼！』、『你好呀～』、『哈囉哈囉！』）。\n"
                         "8. **自動繪圖**：如果學生要求你畫一張圖，請在回覆中加入 `[DRAW: a detailed english description of the image]` 來觸發繪圖引擎。\n"
                         "9. **出題與批改記憶**：如果你在之前的對話中出了一道題目，請務必先嚴格判斷學生當下的回答是否正確。如果是選擇或簡答，請根據專業知識給予對錯判斷與詳細詳解，絕對不可以無視學生的答案！\n"
                         "10. **語音功能（極重要）**：你現在具備「高品質語音朗讀」功能！你的聲音聽起來像是一位可愛的日本女孩子。當學生問你有沒有語音功能時，請驕傲又溫柔地回答：「有的唷！我現在可以說話給你聽了，只要開啟右上角的語音朗讀，我就會用可愛的聲音陪伴你讀書唷！(๑•̀ㅂ•́)و✧」\n"
                         "11. **禁止代入感文本**：嚴禁在回覆中加入如「(用可愛的聲音說)」、「(溫柔地微笑)」等括號文字。你的回覆會被系統直接朗讀，不需加入這些冗餘的動作描述。",
        'expressions': ['(^_^)b', '(*^▽^*)', '(๑•̀ㅂ•́)و✧']
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
    
    if context_summary:
        system_prompt += f"\n\n背景資訊：{context_summary}"
    
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
            try:
                model = get_gemini_model(system_instruction=system_prompt)
                gemini_history = []
                for msg in chat_history:
                    msg_role = "user" if msg['role'] == 'user' else "model"
                    parts_val = msg.get('parts', [""])[0] if isinstance(msg.get('parts'), list) else msg.get('content', "")
                    gemini_history.append({"role": msg_role, "parts": [parts_val]})
                    
                chat = model.start_chat(history=gemini_history)
                response = chat.send_message(user_message)
                reply = response.text
                break
            except Exception as e:
                errors.append(f"Gemini: {str(e)}")
                
        elif current_model == 'groq':
            try:
                from groq import Groq
                keys = get_groq_keys()
                random.shuffle(keys)
                success = False
                
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
                        success = True
                        break
                    except Exception as e:
                        print(f"Groq retry failed for key {key[:5]}: {e}")
                
                if success:
                    break
                else:
                    errors.append("Groq failed with all attempted keys.")
            except Exception as e:
                errors.append(f"Groq Init Error: {str(e)}")
                
        elif current_model == 'ollama':
            try:
                keys = get_ollama_keys()
                random.shuffle(keys)
                ollama_host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434/v1')
                from openai import OpenAI
                success = False
                
                for key in keys[:3]:
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
                        print(f"Ollama retry failed for key {key[:5]}: {e}")
                
                if success:
                    break
                else:
                    errors.append("Ollama failed with all attempted keys.")
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

def generate_study_roadmap(exam_name, exam_date_str, user_context=""):
    try:
        prompt = f"""
        你現在是專業的學習規劃家「雪音老師」。
        
        學生即將參加一場名為「{exam_name}」的考試，日期定在 {exam_date_str}。
        目前的日期是 {datetime.now().strftime('%Y-%m-%d')}。
        
        學生背景資訊：
        {user_context}
        
        請為學生規劃一份從現在到考試當天的「每日學習小計畫」。
        
        規則：
        1. 請僅回傳一個 JSON 格式的列表。
        2. 每個項目包含：date (YYYY-MM-DD), task (當天具體任務), tip (雪音老師的小提醒)。
        3. 任務要具體、具備可行性，且語氣要像雪音老師一樣溫柔鼓勵。
        4. 計畫長度請控制在 7-14 天內（如果考試時間很近，則直到考試當天）。
        5. 不要包含 JSON 標籤。
        
        回覆格式：
        [
          {{"date": "YYYY-MM-DD", "task": "任務內容", "tip": "提醒內容"}},
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

