from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import Question, Mistake
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
        return jsonify({'result': analysis_result})
        
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
    return jsonify({'analysis': analysis, 'recommendation': recommendation})

@study.route("/api/generate_ai_question")
@login_required
def generate_question_api():
    subject = request.args.get('subject', '數學')
    from app.utils.ai_helpers import generate_ai_quiz
    quiz_data = generate_ai_quiz(subject)
    
    if 'error' in quiz_data:
        return jsonify(quiz_data), 500
        
    return jsonify(quiz_data)

@study.route("/tutor_chat", methods=['POST'])
@login_required
def tutor_chat():
    user_msg = request.json.get('message', '')
    if not user_msg:
        return jsonify({'error': '空訊息'}), 400
        
    # Get user's recent mistakes for context
    recent_mistakes = Mistake.query.filter_by(user_id=current_user.id, is_resolved=False).limit(3).all()
    context = ""
    if recent_mistakes:
        context = "學生最近在這些題目上遇到困難：" + ", ".join([m.question.subject for m in recent_mistakes])

    reply = get_ai_tutor_response([], user_msg, personality_key=current_user.ai_personality, context_summary=context)
    return jsonify({'reply': reply})

