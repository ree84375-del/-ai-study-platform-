import os
import json
import time
import re
from sqlalchemy.exc import IntegrityError
from app import create_app, db
from app.models import Question, APIKeyTracker
from docx import Document
from pdf2docx import Converter
import google.generativeai as genai
from google.generativeai.types import RequestOptions

app = create_app()

def get_gemini_key():
    with app.app_context():
        # Get active gemini key
        key = APIKeyTracker.query.filter_by(provider='gemini', status='active').first()
        if key: return key.api_key
        key = APIKeyTracker.query.filter_by(provider='gemini').first()
        if key: return key.api_key
        return os.environ.get("GEMINI_API_KEY")

def convert_pdf_to_docx(pdf_path):
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        return None
    docx_path = pdf_path.replace('.pdf', '.docx')
    if not os.path.exists(docx_path):
        print(f"Converting {pdf_path} to {docx_path}")
        try:
            cv = Converter(pdf_path)
            cv.convert(docx_path, start=0, end=None)
            cv.close()
        except Exception as e:
            print(f"Error converting {pdf_path}: {e}")
            return None
    return docx_path

def read_docx(docx_path):
    if not docx_path or not os.path.exists(docx_path):
        return ""
    doc = Document(docx_path)
    return "\n".join([p.text for p in doc.paragraphs])

# Use gemini to parse
def extract_questions(q_text, a_text, category, tag):
    prompt = f"""
    You are an expert English teacher. I am providing you with the text extracted from a 'Question Paper' (題目卷) and an 'Answer Paper' (答案卷). 
    Your task is to parse these into a structured JSON array of multiple-choice questions. Do NOT generate explanations if none are provided. Do NOT hallucinate questions.
    
    For each valid multiple-choice question found:
    1. Determine the complete question text. Fill `content_text`.
    2. Identify the 4 options A, B, C, D (if available). Fill `option_a`, `option_b`, `option_c`, `option_d`.
    3. Find the corresponding correct answer from the 'Answer Paper'. Fill `correct_answer` with ONLY the letter: A, B, C, or D.
    4. If the 'Answer Paper' provides any explanation or translations for the question, include it in `explanation`. Otherwise leave it empty.
    
    Question Paper Text:
    {q_text}
    
    Answer Paper Text:
    {a_text}
    
    Output strictly a valid JSON array of objects with keys:
    "content_text", "option_a", "option_b", "option_c", "option_d", "correct_answer", "explanation"
    Only output the raw JSON array without markdown formatting. Exclude empty or invalid questions.
    """
    api_key = get_gemini_key()
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-2.5-flash', generation_config={"response_mime_type": "application/json"})
    
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    retries = 3
    for attempt in range(retries):
        try:
            response = model.generate_content(
                prompt, 
                request_options=RequestOptions(timeout=120),
                safety_settings=safety_settings
            )
            if not response.candidates or not response.candidates[0].content.parts:
                if response.candidates:
                    print(f"Blocked by safety: {response.candidates[0].safety_ratings}")
                else:
                    print("Empty response candidates.")
                time.sleep(2)
                continue
            
            text = response.candidates[0].content.parts[0].text
            try:
                result = json.loads(text)
            except json.JSONDecodeError:
                # Use regex to find json
                json_match = re.search(r'\[.*\]', text, re.DOTALL)
                if json_match:
                    result = json.loads(json_match.group(0))
                else:
                    return []
                    
            if isinstance(result, dict):
                result = [result]
                
            return [r for r in result if isinstance(r, dict) and "content_text" in r]
        except Exception as e:
            if 'response' in locals() and hasattr(response, 'candidates') and len(response.candidates) > 0:
                print(f"Safety/block info: {len(response.candidates)} candidates returned")
            print(f"Failed to generate/parse JSON (attempt {attempt+1}): {e}")
            if "429" in str(e):
                time.sleep(10)
            else:
                time.sleep(2)
    return []

def main():
    files = [
        r"C:\Users\Good PC\Downloads\英語第六冊_文法要點單元_used to 的用法_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第六冊_文法要點單元_used to 的用法_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第一冊_語言學習結構內容_Who 引導的問句及答句_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第一冊_語言學習結構內容_Who 引導的問句及答句_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第一冊_語言學習結構內容_What 引導的問句及答句，代名詞所有格_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第二冊_語言學習結構內容_What 引導的問句_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第二冊_語言學習結構內容_What 引導的問句_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第二冊_語言學習結構內容_問時間，基數 (1~60)_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第二冊_語言學習結構內容_現在簡單式句型 ( 含肯定句，否定句，疑問句 ) ， some, any_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第二冊_語言學習結構內容_a lot of lots of many much some a few a little的用法gave 授與動詞用法_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第二冊_語言學習結構內容_a lot of lots of many much some a few a little的用法gave 授與動詞用法_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第三冊_語言學習結構內容_未來式 will, be going to, 包含直述疑問否定_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第三冊_語言學習結構內容_未來式 will, be going to, 包含直述疑問否定_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第三冊_語言學習結構內容_頻率副詞及問句（含程度及情狀副詞）_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第三冊_語言學習結構內容_不規則動詞過去式 ( 含規則過去式動詞 )_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第三冊_語言學習結構內容_不規則動詞過去式 ( 含規則過去式動詞 )_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第四冊_語言學習結構內容_動名詞用法_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第四冊_語言學習結構內容_動名詞用法_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第四冊_語言學習結構內容_情緒動詞及情緒形容詞 ( 原形動詞、過去分詞、現在分詞）_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第四冊_語言學習結構內容_情緒動詞及情緒形容詞 ( 原形動詞、過去分詞、現在分詞）_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第四冊_語言學習結構內容_人稱所有代名詞（含主格所有格及反身代名詞 及 whose ）_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第四冊_語言學習結構內容_形容詞、副詞 ( 原級、比較級、最高級 )_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第四冊_語言學習結構內容_形容詞、副詞 ( 原級、比較級、最高級 )_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_形容詞 & 副詞_答案卷 (1).pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_形容詞 & 副詞_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_形容詞 & 副詞_題目卷 (1).pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_形容詞 & 副詞_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_形容詞原級、比較級、最高級_答案卷 (1).pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_形容詞原級、比較級、最高級_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_形容詞原級、比較級、最高級_題目卷 (1).pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_形容詞原級、比較級、最高級_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_疑問詞when, what time, 疑問詞when, what time, much_答案卷 (1).pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_疑問詞when, what time, 疑問詞when, what time, much_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_疑問詞when, what time, 疑問詞when, what time, much_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_疑問詞where, what, how 和 There isare 句型_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_動詞＋ 不定詞原形動詞Ving_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_疑問詞where, what, how 和 There isare 句型_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_動詞＋ 不定詞原形動詞Ving_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_動詞時態綜合應用_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_動詞時態綜合應用_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_祈使句、動名詞、不定詞_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_祈使句、動名詞、不定詞_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_(過去、現在、未來)單純式與進行式_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_(過去、現在、未來)單純式與進行式_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_祈使句、現在單純式、現在進行式_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_祈使句、現在單純式、現在進行式_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_be (am, are, is)_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第五冊_文法診斷_be (am, are, is)_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第六冊_閱讀測驗_閱讀測驗_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第六冊_閱讀測驗_閱讀測驗_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第六冊_文法測驗_文法測驗_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第六冊_文法測驗_文法測驗_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第六冊_對話測驗_對話測驗_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第六冊_對話測驗_對話測驗_題目卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第六冊_文法要點單元_介詞的使用彙整（一）_答案卷.pdf",
        r"C:\Users\Good PC\Downloads\英語第六冊_文法要點單元_介詞的使用彙整（一）_題目卷.pdf"
    ]
    
    # Filter files that actually exist
    files = [f for f in files if os.path.exists(f)]
    
    # Group logic
    groups = {}
    for file in files:
        base_name = os.path.basename(file).replace('.pdf', '')
        base_name = re.sub(r'_\s*答案卷.*', '', base_name)
        base_name = re.sub(r'_\s*題目卷.*', '', base_name)
        
        if base_name not in groups:
            groups[base_name] = {'q': [], 'a': []}
        if '題目' in file:
            groups[base_name]['q'].append(file)
        if '答案' in file:
            groups[base_name]['a'].append(file)

    total_added = 0
    
    with app.app_context():
        # Load existing exact content_text to prevent duplicates perfectly
        db_qs = {q.content_text: True for q in Question.query.all()}
        
        for group_name, paths in groups.items():
            print(f"--- Processing group: {group_name} ---")
            
            # Read all unique Qs and As for this group
            q_texts = ""
            for q_pdf in set(paths['q']):
                docx_path = convert_pdf_to_docx(q_pdf)
                q_texts += read_docx(docx_path) + "\n"
                
            a_texts = ""
            for a_pdf in set(paths['a']):
                docx_path = convert_pdf_to_docx(a_pdf)
                a_texts += read_docx(docx_path) + "\n"
                
            if not q_texts.strip():
                print(f"Skipping {group_name} due to empty Question text")
                continue
                
            print(f"Extracting JSON for {group_name}...")
            parts = group_name.split('_')
            category = f"{parts[0]}_{parts[1]}" if len(parts) > 1 else group_name
            tag = parts[2] if len(parts) > 2 else category
            if len(parts) > 3:
                tag += " " + parts[3]
            
            extracted = extract_questions(q_texts, a_texts, category, tag)
            print(f"Parsed {len(extracted)} potential questions from {group_name}.")
            
            added_this_group = 0
            for item in extracted:
                if not item.get("content_text"):
                    continue
                content_text = item.get("content_text", "").strip()
                if not content_text or len(content_text) < 5:
                    continue
                
                if content_text in db_qs:
                    continue
                
                correct = str(item.get("correct_answer", ""))
                ans_match = re.search(r'[A-Da-d]', correct)
                correct_letter = ans_match.group(0).upper() if ans_match else "A"
                
                try:
                    new_q = Question(
                        subject="英文",
                        category=category[:100],
                        tags=tag[:100],
                        content_text=content_text,
                        option_a=str(item.get("option_a", ""))[:255],
                        option_b=str(item.get("option_b", ""))[:255],
                        option_c=str(item.get("option_c", ""))[:255],
                        option_d=str(item.get("option_d", ""))[:255],
                        correct_answer=correct_letter,
                        explanation=str(item.get("explanation", "")),
                        difficulty=2 # Defaulting to 2 for these exercises
                    )
                    db.session.add(new_q)
                    db_qs[content_text] = True
                    total_added += 1
                    added_this_group += 1
                except Exception as e:
                    print(f"Error preparing Question model: {e}")
            
            try:
                db.session.commit()
                print(f"Saved {added_this_group} questions for {group_name} to DB.")
            except IntegrityError:
                db.session.rollback()
                print("Integrity Error during commit, skipping this batch.")
            
            time.sleep(1.5)

        print(f"====== FINISHED ======")
        print(f"Total NEW unique questions added: {total_added}")

if __name__ == "__main__":
    main()
