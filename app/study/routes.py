from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
from app.models import Question, Mistake
from app import db
from app.utils.ai_helpers import analyze_question_image, get_ai_tutor_response
import random

study = Blueprint('study', __name__)

@study.route("/practice", methods=['GET', 'POST'])
@login_required
def practice():
    if request.method == 'POST':
        question_id = request.form.get('question_id')
        user_answer = request.form.get('answer')
        
        question = Question.query.get_or_404(question_id)
        is_correct = (user_answer == question.correct_answer)
        
        if not is_correct:
            # Record mistake
            mistake = Mistake.query.filter_by(user_id=current_user.id, question_id=question_id).first()
            if mistake:
                mistake.mistake_count += 1
                mistake.is_resolved = False
            else:
                mistake = Mistake(user_id=current_user.id, question_id=question_id)
                db.session.add(mistake)
            db.session.commit()
            
        return jsonify({
            'correct': is_correct,
            'correct_answer': question.correct_answer,
            'explanation': question.explanation
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
        analysis_result = analyze_question_image(image_bytes)
        
        return jsonify({'result': analysis_result})
        
    return render_template('ai_vision.html', title='圖片解題')

@study.route("/tutor_chat", methods=['POST'])
@login_required
def tutor_chat():
    user_msg = request.json.get('message', '')
    if not user_msg:
        return jsonify({'error': '空訊息'}), 400
        
    # Simplified chat (stateless for demo)
    reply = get_ai_tutor_response([], user_msg)
    return jsonify({'reply': reply})

