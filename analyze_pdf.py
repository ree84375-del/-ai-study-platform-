import os
import sys
import traceback
import google.generativeai as genai
from dotenv import load_dotenv

# Load env vars
load_dotenv('.env')

# Configure Gemini
api_key = os.environ.get('GEMINI_API_KEY')
if not api_key:
    keys = os.environ.get('GEMINI_API_KEYS', '').split(',')
    if keys and keys[0]:
        api_key = keys[0]

if not api_key:
    print("Error: No Gemini API key found.")
    sys.exit(1)

genai.configure(api_key=api_key)

pdf_path = r"C:\Users\Good PC\Downloads\113P_Math.pdf"

if not os.path.exists(pdf_path):
    print(f"Error: File not found at {pdf_path}")
    sys.exit(1)

try:
    print("Uploading PDF to Gemini...")
    uploaded_file = genai.upload_file(path=pdf_path)
    print(f"Uploaded file '{uploaded_file.display_name}' as: {uploaded_file.uri}")

    model = genai.GenerativeModel('gemini-2.5-pro')
    prompt = """
    這是一份數學試卷的 PDF 等。
    請幫我算出這份試卷中「總共有幾題」。
    
    規則：
    1. 不用包含前面的考試說明、測驗簡介。
    2. 不用包含「非選擇題」或「混合題」中需要手寫計算過程的子題（如果混合題裡面有單純的選擇題，可以算）。
    3. 只需要計算單選題、多選題、選填題的總題數。
    
    請回覆我總題數，並且簡單列出各部分的題數（例如：單選X題，多選Y題，選填Z題）。
    """
    
    print("Generating content...")
    response = model.generate_content([uploaded_file, prompt])
    
    with open("result.txt", "w", encoding="utf-8") as f:
        f.write("--- Gemini Analysis ---\n")
        f.write(response.text)
        
    print("Done. Result saved to result.txt")
    
except Exception as e:
    with open("error.txt", "w", encoding="utf-8") as f:
        f.write(f"An error occurred: {e}\n")
        traceback.print_exc(file=f)
    print("Error saved to error.txt")
