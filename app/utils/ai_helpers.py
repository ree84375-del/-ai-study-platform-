import os
import google.generativeai as genai
from PIL import Image
import io

# Setup Gemini API key
def get_gemini_model():
    # Use the first key provided by user, or allow it to fail gracefully if none is valid
    api_key = os.environ.get('GEMINI_API_KEY')
    if api_key:
         genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.5-flash')

def analyze_question_image(image_bytes):
    try:
        model = get_gemini_model()
        image = Image.open(io.BytesIO(image_bytes))
        prompt = """
        你是一個專業的家教老師。請看這張圖片中的題目，並完成以下任務：
        1. 辨識並原封不動地打出圖中的題目文字 (如果是選擇題，請把選項也列出來)。
        2. 給出正確答案。
        3. 給出詳細、一步一步的解題過程與觀念講解。
        
        請用清晰的排版（可以使用 Markdown 語法）回覆。
        """
        response = model.generate_content([prompt, image])
        return response.text
    except Exception as e:
        return f"解析圖片時發生錯誤：{str(e)}\n(請確認是否已設定正確的 GEMINI_API_KEY 環境變數)"

def get_ai_tutor_response(chat_history, user_message):
     try:
         model = get_gemini_model()
         # chat_history format should be a list of dicts: [{'role': 'user', 'parts': ['msg']}, {'role': 'model', 'parts': ['msg']}]
         chat = model.start_chat(history=chat_history)
         
         # System instruction context (injected into the prompt for this simple implementation)
         system_prompt = "你是一個溫柔、有耐心且充滿日系輕小說風格的專屬線上家教「雪音(Yukine)老師」。請用繁體中文回答學生的問題。如果學生問跟學習無關的，請溫柔地引導回學習上。\n學生說："
         
         response = chat.send_message(system_prompt + user_message)
         return response.text
     except Exception as e:
         return f"AI 老師暫時離開了座位：{str(e)}"
