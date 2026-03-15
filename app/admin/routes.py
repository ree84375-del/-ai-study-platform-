import os
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import User, Question, ChatSession, Group, Announcement
from app import db
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
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
    # --- DATABASE HEALTH CHECK (Auto-Migration) ---
    try:
        db.session.execute(text("SELECT group_type FROM \"group\" LIMIT 1"))
    except ProgrammingError:
        db.session.rollback()
        auto_fixes = [
            "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES group_message(id)",
            "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS is_edited BOOLEAN DEFAULT FALSE",
            "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS is_recalled BOOLEAN DEFAULT FALSE",
            "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE",
            "ALTER TABLE assignment ADD COLUMN IF NOT EXISTS reference_answer TEXT",
            "ALTER TABLE assignment ADD COLUMN IF NOT EXISTS reference_image VARCHAR(255)",
            "ALTER TABLE assignment ADD COLUMN IF NOT EXISTS due_date TIMESTAMP",
            "ALTER TABLE assignment ADD COLUMN IF NOT EXISTS description TEXT",
            "ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS submission_image VARCHAR(255)",
            "ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS recognized_content TEXT",
            "ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS feedback TEXT",
            "ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS score INTEGER",
            "ALTER TABLE \"group\" ADD COLUMN IF NOT EXISTS group_type VARCHAR(20) DEFAULT 'class'"
        ]
        for stmt in auto_fixes:
            try:
                db.session.execute(text(stmt))
                db.session.commit()
            except: db.session.rollback()
    # --- END DATABASE HEALTH CHECK ---

    users = User.query.order_by((User.role == 'admin').desc(), User.id).all()
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
            from app.utils.ai_helpers import generate_text_with_fallback
            reply = generate_text_with_fallback(command, system_instruction="你是雪音，目前是後台管理員正在對你下達專屬測試與系統指令，請絕對服從並精確回答。")
            flash(f'雪音後台回應：{reply}', 'info')
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

@admin.route('/announcements')
def announcements():
    announcements_list = Announcement.query.order_by(Announcement.id.desc()).all()
    return render_template('admin/announcements.html', announcements=announcements_list)

@admin.route('/announcements/new', methods=['GET', 'POST'])
def new_announcement():
    if request.method == 'POST':
        title = request.form.get('title')
        content = request.form.get('content')
        if title and content:
            announcement = Announcement(title=title, content=content, created_by_id=current_user.id)
            db.session.add(announcement)
            db.session.commit()
            flash('系統公告發布成功！', 'success')
            return redirect(url_for('admin.announcements'))
        else:
            flash('標題與內容不能為空。', 'danger')
            
    return render_template('admin/announcement_edit.html')

@admin.route('/announcements/ai_generate', methods=['POST'])
def ai_generate_announcement():
    from flask import jsonify
    prompt = request.form.get('prompt')
    if not prompt:
        flash('請輸入公告綱要。', 'danger')
        return redirect(url_for('admin.new_announcement'))
        
    try:
        from app.utils.ai_helpers import generate_text_with_fallback
        text = generate_text_with_fallback(prompt, system_instruction="你是「雪音」，AI 學習平台的系統管理員助理。請根據使用者提供的綱要，撰寫一篇生動、友善且帶有溫度的全站公告。語氣要活潑專業，可以適度使用 emoji。回傳必須為 JSON 格式：{\"title\": \"公告標題\", \"content\": \"公告內容（請包含對平台學生的問候）\"}。除了 JSON 之外，請勿回傳任何其他多餘的字或 Markdown syntax。").strip()
        
        if text.startswith('```json'):
            text = text[7:]
        if text.endswith('```'):
            text = text[:-3]
            
        import json
        data = json.loads(text)
        
        return jsonify({
            'status': 'success',
            'title': data.get('title', '系統公告'),
            'content': data.get('content', prompt)
        })
        
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@admin.route('/announcements/delete/<int:obj_id>', methods=['POST'])
def delete_announcement(obj_id):
    announcement = Announcement.query.get_or_404(obj_id)
    try:
        db.session.delete(announcement)
        db.session.commit()
        flash('公告已成功刪除！', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'刪除失敗：{str(e)}', 'danger')
        
    return redirect(url_for('admin.announcements'))
