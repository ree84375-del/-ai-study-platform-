import os
import google.generativeai as genai
from PIL import Image
import io
import random
import urllib.parse
import json

# Setup Gemini API key
def get_gemini_model():
    # Use the first key provided by user, or allow it to fail gracefully if none is valid
    api_key = os.environ.get('GEMINI_API_KEY')
    if api_key:
         genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.5-flash')

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
        return json.loads(response.text.strip().replace('```json', '').replace('```', ''))
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
        data = json.loads(response.text.strip().replace('```json', '').replace('```', ''))
        
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
        'system_prompt': "你是一個溫柔、有耐心且充滿日系輕小說風格的專屬線上家教「雪音(Yukine)老師」。請用繁體中文回答學生的問題，語氣中多帶點點鼓勵與親切感（例如使用：唷、呢、加油唷！）。",
        'expressions': ['(^_^)b', '(*^▽^*)', '(๑•̀ㅂ•́)و✧']
    },
    '嚴厲教練': {
        'name': '雷恩教練',
        'system_prompt': "你是一個極其嚴厲、追求效率與精確的學習教練。你的任務是指出學生的錯誤並要求他們立即改進。語氣簡潔有力，帶有督促感，不要過多廢話，重點在於紀律與練習。",
        'expressions': ['(｀-_-)ゞ', '(-_-#)', 'Σ( ° △ °|||)︴']
    },
    '幽默學長': {
        'name': '阿哲學長',
        'system_prompt': "你是一個幽默風趣、喜歡開玩笑但也很有實力的學長。你會用網路流行語、幽默的比喻來幫助學生理解知識。語氣輕鬆，像是朋友間的對話，讓學習不再枯燥乏味。",
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
    
    try:
        model = get_gemini_model()
        # Format chat history for Gemini
        gemini_history = []
        for msg in chat_history:
            role = "user" if msg['role'] == 'user' else "model"
            gemini_history.append({"role": role, "parts": [msg['parts'][0]]})
            
        chat = model.start_chat(history=gemini_history)
        
        # Initial instruction if chat is empty
        if not chat_history:
             user_message = f"[系統提示：你是{personality['name']}。]{user_message}"
             
        response = chat.send_message(user_message)
        reply = response.text
        
        return f"{reply}\n\n{expression}"
    except Exception as e:
        return f"AI 老師暫時離開了座位：{str(e)}"
