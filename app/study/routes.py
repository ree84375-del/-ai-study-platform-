from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import Question, Mistake, ChatSession, ChatMessage
from app import db
from app.utils.ai_helpers import analyze_question_image, get_ai_tutor_response, AI_PERSONALITIES, auto_tag_question, detect_duplicate_question, get_knowledge_graph_recommendation
import random
from datetime import datetime, timedelta, timezone

study = Blueprint('study', __name__)

@study.route("/practice", methods=['GET', 'POST'])
@login_required
def practice():
    if request.method == 'POST':
        question_id = request.form.get('question_id')
        user_answer = request.form.get('answer')
        
        question = Question.query.get_or_404(question_id)
        is_correct = (user_answer == question.correct_answer)
        
        mistake = Mistake.query.filter_by(user_id=current_user.id, question_id=question_id).first()
        
        if is_correct:
            # SRS Logic for correct answer
            if mistake:
                mistake.srs_level = min(mistake.srs_level + 1, 7)
                intervals = [0, 1, 2, 4, 7, 14, 30, 60]
                mistake.last_interval = intervals[mistake.srs_level]
                mistake.next_review_date = datetime.now(timezone.utc) + timedelta(days=mistake.last_interval)
                if mistake.srs_level >= 4: # Consider resolved if reached a high level
                    mistake.is_resolved = True
            db.session.commit()
        else:
            # SRS Logic for wrong answer
            if mistake:
                mistake.mistake_count += 1
                mistake.srs_level = max(mistake.srs_level - 1, 0) # Drop one level
                mistake.is_resolved = False
            else:
                mistake = Mistake(user_id=current_user.id, question_id=question_id)
                db.session.add(mistake)
            
            # Reset review clock for wrong answer
            mistake.next_review_date = datetime.now(timezone.utc) + timedelta(hours=1)
            db.session.commit()
            
        return jsonify({
            'correct': is_correct,
            'correct_answer': question.correct_answer,
            'explanation': question.explanation,
            'srs_level': mistake.srs_level if mistake else 0
        })

    # GET request - fetch random questions
    subject_filter = request.args.get('subject')
    query = Question.query
    if subject_filter:
        query = query.filter_by(subject=subject_filter)
        
    questions = query.all()
    if not questions:
        flash('目前題庫中沒有題目。', 'info')
        return redirect(url_for('main.home'))
        
    question = random.choice(questions)
    return render_template('practice.html', title='測驗練習', question=question)

@study.route("/mistakes")
@login_required
def mistakes():
    mistake_records = Mistake.query.filter_by(user_id=current_user.id, is_resolved=False).all()
    return render_template('mistakes.html', title='錯題本', mistakes=mistake_records)


@study.route("/ai_vision", methods=['GET', 'POST'])
@login_required
def ai_vision():
    if request.method == 'POST':
        if 'image' not in request.files:
            return jsonify({'error': '沒有上傳圖片'}), 400
            
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': '未選擇檔案'}), 400
            
        image_bytes = file.read()
        
        # New mode: Quick OCR to Quiz
        mode = request.form.get('mode', 'analyze')
        if mode == 'ocr_to_quiz':
            from app.utils.ai_helpers import parse_question_from_image
            data = parse_question_from_image(image_bytes)
            if 'error' in data:
                return jsonify(data), 500
            
            # Auto-tagging and Duplicate detection
            content = data.get('content_text', '')
            existing_questions = [q.content_text for q in Question.query.all()]
            if detect_duplicate_question(content, existing_questions):
                 return jsonify({'error': '偵測到重複題目，已取消儲存。'}), 400
            
            tags = data.get('tags') or auto_tag_question(content)
            
            new_q = Question(
                subject=data.get('subject', '未分類'),
                content_text=content,
                option_a=data.get('option_a'),
                option_b=data.get('option_b'),
                option_c=data.get('option_c'),
                option_d=data.get('option_d'),
                correct_answer=data.get('correct_answer', 'A'),
                explanation=data.get('explanation', ''),
                tags=tags
            )
            db.session.add(new_q)
            db.session.commit()
            return jsonify({'status': 'success', 'question_id': new_q.id, 'data': data})
        
        # Default analysis mode
        analysis_result = analyze_question_image(image_bytes)
        
        # Create a chat session for the vision analysis
        session = ChatSession(user_id=current_user.id, title="圖片解題分析")
        db.session.add(session)
        db.session.commit()
        
        ai_msg = ChatMessage(session_id=session.id, role='ai', content=analysis_result)
        db.session.add(ai_msg)
        db.session.commit()

        return jsonify({'result': analysis_result, 'session_id': session.id})
        
    return render_template('ai_vision.html', title='圖片解題')

@study.route("/analyze_mistake/<int:mistake_id>")
@login_required
def analyze_mistake(mistake_id):
    mistake = Mistake.query.get_or_404(mistake_id)
    if mistake.user_id != current_user.id:
        return jsonify({'error': '權限不足'}), 403
    
    question = mistake.question
    recommendation = get_knowledge_graph_recommendation(question.subject)
    
    prompt = f"""
    這是一個學生的錯題。請分析可能的錯誤原因（例如：觀念不清、計算錯誤、題目陷阱等）。
    題目：{question.content_text}
    正確答案：{question.correct_answer}
    解釋：{question.explanation}
    
    知識圖譜建議：如果學生這題不懂，建議他先去複習「{recommendation}」。
    請用{current_user.ai_personality or '雪音-溫柔型'}的語氣來給予建議。
    """
    
    analysis = get_ai_tutor_response([], prompt, personality_key=current_user.ai_personality)
    
    # Optional: Automatically create a chat session for this analysis
    session = ChatSession(user_id=current_user.id, title=f"分析錯題: {question.content_text[:15]}...")
    db.session.add(session)
    db.session.commit()
    
    ai_msg = ChatMessage(session_id=session.id, role='ai', content=analysis)
    db.session.add(ai_msg)
    db.session.commit()

    return jsonify({'analysis': analysis, 'recommendation': recommendation, 'session_id': session.id})

@study.route("/api/generate_ai_question")
@login_required
def generate_question_api():
    subject = request.args.get('subject', '數學')
    from app.utils.ai_helpers import generate_ai_quiz
    quiz_data = generate_ai_quiz(subject)
    
    if 'error' in quiz_data:
        return jsonify(quiz_data), 500
        
    # Save to database
    new_q = Question(
        subject=subject,
        content_text=quiz_data.get('content_text'),
        option_a=quiz_data.get('option_a'),
        option_b=quiz_data.get('option_b'),
        option_c=quiz_data.get('option_c'),
        option_d=quiz_data.get('option_d'),
        correct_answer=quiz_data.get('correct_answer'),
        explanation=quiz_data.get('explanation'),
        tags=quiz_data.get('tags')
    )
    db.session.add(new_q)
    db.session.commit()
    
    return jsonify({'status': 'success', 'question_id': new_q.id, 'quiz': quiz_data})

@study.route("/tutor_chat", methods=['POST'])
@login_required
def tutor_chat():
    try:
        user_msg = request.json.get('message', '')
        session_id = request.json.get('session_id')
        
        if not user_msg:
            return jsonify({'error': '空訊息'}), 400
            
        # Get or create session
        if session_id:
            session = ChatSession.query.get_or_404(session_id)
            if session.user_id != current_user.id:
                return jsonify({'error': '權限不足'}), 403
        else:
            session = ChatSession(user_id=current_user.id, title=user_msg[:20])
            db.session.add(session)
            db.session.commit()

        # Save user message
        user_chat = ChatMessage(session_id=session.id, role='user', content=user_msg)
        db.session.add(user_chat)
        
        # Get recent mistakes for context
        context = ""
        if not session_id:
            try:
                recent_mistakes = Mistake.query.filter_by(user_id=current_user.id, is_resolved=False).limit(3).all()
                if recent_mistakes:
                    context = "學生最近在這些題目上遇到困難：" + ", ".join([m.question.subject for m in recent_mistakes])
            except Exception:
                pass

        # Convert session messages to Gemini format
        history_override = request.json.get('history')
        if history_override:
            recent_history = history_override
        else:
            try:
                history = [{'role': str(m.role), 'parts': [str(m.content)]} for m in session.messages]
                recent_history = history[:-1] if len(history) > 0 else []
            except Exception:
                recent_history = []

        reply = get_ai_tutor_response(recent_history, user_msg, personality_key=current_user.ai_personality, context_summary=context)
        
        # Save AI response
        try:
            ai_chat = ChatMessage(session_id=session.id, role='ai', content=reply)
            db.session.add(ai_chat)
            db.session.commit()
        except Exception:
            db.session.rollback()
        
        return jsonify({'reply': reply, 'session_id': session.id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'reply': f'AI 老師暫時離開了座位：{str(e)}', 'error': str(e)}), 200

@study.route("/api/chat/sessions")
@login_required
def get_chat_sessions():
    sessions = ChatSession.query.filter_by(user_id=current_user.id).order_by(ChatSession.created_at.desc()).all()
    return jsonify([{'id': s.id, 'title': s.title, 'created_at': s.created_at.isoformat()} for s in sessions])

@study.route("/api/chat/history/<int:session_id>")
@login_required
def get_chat_history(session_id):
    session = ChatSession.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        return jsonify({'error': '權限不足'}), 403
    messages = [{'role': m.role, 'content': m.content} for m in session.messages]
    return jsonify({'messages': messages})

@study.route("/lofi")
@login_required
def lofi_room():
    return render_template('lofi.html', title='深夜陪讀室')

@study.route("/generate_exam")
@login_required
def generate_exam():
    mistakes = Mistake.query.filter_by(user_id=current_user.id, is_resolved=False).order_by(Mistake.mistake_count.desc()).limit(5).all()
    if not mistakes:
        flash("目前沒有足夠的錯題來生成測驗。請先進行練習！", "info")
        return redirect(url_for('study.practice'))
    return render_template('exam.html', title='專屬模擬考', mistakes=mistakes)

@study.route("/ai_docs", methods=['GET', 'POST'])
@login_required
def ai_docs():
    if request.method == 'POST':
        if 'file' not in request.files:
            return jsonify({'error': '沒有上傳檔案'}), 400
        file = request.files['file']
        if file.filename == '' or not file.filename.endswith('.pdf'):
            return jsonify({'error': '請上傳 PDF 格式的講義'}), 400
        import PyPDF2
        import io
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file.read()))
        full_text = ""
        for i in range(min(len(pdf_reader.pages), 5)):
            full_text += pdf_reader.pages[i].extract_text() + "\n"
        if not full_text.strip():
            return jsonify({'error': '無法從 PDF 中讀取文字，可能是掃描圖檔？請改用圖片解題。'}), 400
        session = ChatSession(user_id=current_user.id, title=f"講義分析: {file.filename}")
        db.session.add(session)
        db.session.commit()
        context_msg = ChatMessage(session_id=session.id, role='ai', 
                                content=f"我已經讀完您的講義「{file.filename}」了！您可以開始問我關於這份講義的問題。")
        db.session.add(context_msg)
        db.session.commit()
        return jsonify({'status': 'success', 'session_id': session.id})
    return render_template('ai_docs.html', title='講義分析')

