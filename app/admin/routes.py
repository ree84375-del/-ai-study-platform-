import os
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import User
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
    return render_template('admin/dashboard.html', title="管理員後台", users=users, gemini_keys=gemini_keys, groq_keys=groq_keys)

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
