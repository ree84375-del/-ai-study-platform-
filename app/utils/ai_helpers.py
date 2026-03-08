import os
import google.generativeai as genai
from PIL import Image
import io
import random
import urllib.parse

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
        prompt = """你是一個專業的家教老師。請看這張圖片中的題目，完成三個任務：1. 辨識文字、2. 給答案、3. 詳細解題。"""
        response = model.generate_content([prompt, image])
        return response.text
    except Exception as e:
        return f"解析時發生錯誤：{str(e)}"

def generate_image_url(prompt):
    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=600&nologo=true"
    return f"![生成圖片]({url})"

def get_ai_tutor_response(chat_history, user_message, model_choice='gemini'):
    if user_message.strip().startswith('/image '):
        prompt = user_message.replace('/image ', '', 1).strip()
        return f"為您生成繪圖：**{prompt}**\n\n" + generate_image_url(prompt)

    system_prompt = "你是一個溫柔、有耐心且充滿日系輕小說風格的專屬線上家教「雪音(Yukine)老師」。請用繁體中文回答學生的問題。"
    
    try:
        if model_choice == 'groq':
            client = get_groq_client()
            chat_completion = client.chat.completions.create(
                messages=[{"role": "system", "content": system_prompt}] + 
                         [{"role": msg['role'], "content": msg['parts'][0]} for msg in chat_history] +
                         [{"role": "user", "content": user_message}],
                model="llama3-70b-8192",
            )
            return chat_completion.choices[0].message.content
        else:
            model = get_gemini_model()
            chat = model.start_chat(history=chat_history)
            response = chat.send_message(system_prompt + "學生說：" + user_message)
            return response.text
    except Exception as e:
        return f"AI 老師暫時離開了座位：{str(e)}"
