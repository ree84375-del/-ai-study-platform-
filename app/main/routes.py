from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db
from datetime import datetime, timezone

main = Blueprint('main', __name__)

@main.before_app_request
def before_request():
    if current_user.is_authenticated:
        try:
            current_user.last_active_at = datetime.now(timezone.utc)
            db.session.commit()
        except Exception:
            db.session.rollback()

@main.route("/")
@main.route("/home")
def home():
    # Ensure CSRF is active for templates using hidden fields/JS
    return render_template('home.html')

@main.route("/about")
def about():
    return render_template('about.html')

@main.route("/privacy")
def privacy():
    return render_template('privacy.html')

@main.route("/terms")
def terms():
    return render_template('terms.html')

@main.route("/api/complete_tour", methods=['POST'])
@login_required
def complete_tour():
    if not current_user.has_seen_tour:
        current_user.has_seen_tour = True
        db.session.commit()
    return jsonify({"status": "success"})

@main.route("/profile")
@login_required
def profile():
    return render_template('profile.html', title='個人檔案')

@main.route("/chat")
@login_required
def chat():
    return render_template('chat.html', title='AI 聊天室')

@main.route("/update_profile", methods=['POST'])
@login_required
def update_profile():
    from app.models import User

    new_username = request.form.get('username', current_user.username)

    # Check for duplicate username (only if it actually changed)
    if new_username != current_user.username:
        existing_user = User.query.filter_by(username=new_username).first()
        if existing_user:
            flash('該使用者名稱已被使用，請選擇其他名稱。', 'danger')
            return redirect(url_for('main.profile'))

    current_user.username = new_username
    current_user.bio = request.form.get('bio', current_user.bio)
    current_user.learning_goals = request.form.get('learning_goals', current_user.learning_goals)
    current_user.ai_personality = request.form.get('ai_personality', current_user.ai_personality)
    current_user.preferred_theme = request.form.get('preferred_theme', current_user.preferred_theme)
    current_user.avatar_url = request.form.get('avatar_url', current_user.avatar_url)

    try:
        db.session.commit()
        flash('您的個人檔案已更新！', 'success')
    except Exception:
        db.session.rollback()
        flash('更新失敗，請稍後再試。', 'danger')

    return redirect(url_for('main.profile'))
