import os
import google.generativeai as genai
from dotenv import load_dotenv
load_dotenv()

key = "AIzaSyD6X6w80bwoP7wcJ6T9Enlw4pdLwdOiA9Y"
genai.configure(api_key=key)

models_to_test = ["gemini-1.5-flash", "gemini-1.5-flash-latest", "gemini-1.0-pro", "gemini-pro"]

for m_name in models_to_test:
    print(f"Testing {m_name}...")
    try:
        model = genai.GenerativeModel(m_name)
        response = model.generate_content("hi", generation_config={"max_output_tokens": 5})
        print(f"  SUCCESS: {m_name}")
    except Exception as e:
        print(f"  FAILED: {m_name} - {e}")
