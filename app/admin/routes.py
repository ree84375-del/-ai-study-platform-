import os
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import User, Question, ChatSession, Group
from app import db
from app.utils.ai_helpers import get_gemini_model

admin = Blueprint('admin', __name__, url_prefix='/admin')

@admin.before_request
@login_required
def require_admin():
    if not current_user.is_admin:
        flash('您沒有權限訪問後台。', 'danger')
        return redirect(url_for('main.home'))

@admin.route('/dashboard')
def dashboard():
    users = User.query.all()
    gemini_keys = os.environ.get('GEMINI_API_KEYS', os.environ.get('GEMINI_API_KEY', ''))
    groq_keys = os.environ.get('GROQ_API_KEYS', '')
    
    stats = {
        'total_users': User.query.count(),
        'total_questions': Question.query.count(),
        'total_chats': ChatSession.query.count(),
        'total_groups': Group.query.count()
    }
    
    return render_template('admin/dashboard.html', title="管理員後台", users=users, gemini_keys=gemini_keys, groq_keys=groq_keys, stats=stats)

@admin.route('/user/<int:user_id>/role', methods=['POST'])
def change_user_role(user_id):
    user = User.query.get_or_404(user_id)
    if user.email == 'ree84375@gmail.com':
        flash('無法更改網站持有人的權限。', 'danger')
        return redirect(url_for('admin.dashboard'))
        
    new_role = request.form.get('role')
    if new_role in ['student', 'teacher', 'admin', 'guest']:
        user.role = new_role
        db.session.commit()
        flash(f'已將 {user.username} 的權限更改為 {new_role}。', 'success')
    else:
        flash('無效的權限設定。', 'danger')
        
    return redirect(url_for('admin.dashboard'))

@admin.route('/user/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.email == 'ree84375@gmail.com' or user.id == current_user.id:
        flash('無法刪除超級管理員或您自己。', 'danger')
        return redirect(url_for('admin.dashboard'))
        
    try:
        from app.models import Mistake, ChatSession, GroupMember, AssignmentStatus
        # 手動刪除關聯資料避免 Foreign Key Constraint 失敗
        Mistake.query.filter_by(user_id=user.id).delete()
        sessions = ChatSession.query.filter_by(user_id=user.id).all()
        for s in sessions:
            db.session.delete(s)
        GroupMember.query.filter_by(user_id=user.id).delete()
        AssignmentStatus.query.filter_by(user_id=user.id).delete()
        
        db.session.delete(user)
        db.session.commit()
        flash(f'已成功刪除用戶 {user.username} 及其相關紀錄。', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'刪除用戶失敗：{str(e)}', 'danger')
        
    return redirect(url_for('admin.dashboard'))

@admin.route('/yukine_command', methods=['POST'])
def yukine_command():
    command = request.form.get('command', '')
    if command:
        try:
            model = get_gemini_model(system_instruction="你是雪音，目前是後台管理員正在對你下達專屬測試與系統指令，請絕對服從並精確回答。")
            res = model.generate_content(command)
            flash(f'雪音後台回應：{res.text}', 'info')
        except Exception as e:
            flash(f'雪音連線失敗：{str(e)}', 'danger')
            
    return redirect(url_for('admin.dashboard'))

@admin.route('/questions')
def questions():
    page = request.args.get('page', 1, type=int)
    questions_pagination = Question.query.order_by(Question.id.desc()).paginate(page=page, per_page=20)
    return render_template('admin/questions.html', questions=questions_pagination.items, pagination=questions_pagination)

@admin.route('/questions/new', methods=['GET', 'POST'])
def new_question():
    if request.method == 'POST':
        question = Question(
            subject=request.form.get('subject'),
            category=request.form.get('category'),
            content_text=request.form.get('content_text'),
            option_a=request.form.get('option_a'),
            option_b=request.form.get('option_b'),
            option_c=request.form.get('option_c'),
            option_d=request.form.get('option_d'),
            correct_answer=request.form.get('correct_answer'),
            explanation=request.form.get('explanation'),
            difficulty=request.form.get('difficulty', type=int)
        )
        db.session.add(question)
        db.session.commit()
        flash('題目已成功新增！', 'success')
        return redirect(url_for('admin.questions'))
        
    return render_template('admin/question_edit.html', title="新增題目", question=None)

@admin.route('/questions/edit/<int:question_id>', methods=['GET', 'POST'])
def edit_question(question_id):
    question = Question.query.get_or_404(question_id)
    if request.method == 'POST':
        question.subject = request.form.get('subject')
        question.category = request.form.get('category')
        question.content_text = request.form.get('content_text')
        question.option_a = request.form.get('option_a')
        question.option_b = request.form.get('option_b')
        question.option_c = request.form.get('option_c')
        question.option_d = request.form.get('option_d')
        question.correct_answer = request.form.get('correct_answer')
        question.explanation = request.form.get('explanation')
        question.difficulty = request.form.get('difficulty', type=int)
        
        db.session.commit()
        flash('題目已成功更新！', 'success')
        return redirect(url_for('admin.questions'))
        
    return render_template('admin/question_edit.html', title="編輯題目", question=question)

@admin.route('/questions/delete/<int:question_id>', methods=['POST'])
def delete_question(question_id):
    question = Question.query.get_or_404(question_id)
    try:
        # 刪除與此題目相關的錯題紀錄 (Mistake) 防止預設 FK Constraint 出錯
        from app.models import Mistake
        Mistake.query.filter_by(question_id=question.id).delete()
        
        db.session.delete(question)
        db.session.commit()
        flash('題目已成功刪除！', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'刪除題目失敗：{str(e)}', 'danger')
        
    return redirect(url_for('admin.questions'))

