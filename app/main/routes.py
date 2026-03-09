from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app import db, bcrypt
from app.models import User, Mistake
from datetime import datetime, timezone

main = Blueprint('main', __name__)

@main.before_app_request
def before_request():
    if current_user.is_authenticated:
        try:
            # Use a direct UPDATE statement to avoid DetachedInstanceError
            # or stale-session issues that cause logouts.
            db.session.execute(
                db.update(User).where(User.id == current_user.id).values(
                    last_active_at=datetime.now(timezone.utc)
                )
            )
            db.session.commit()
        except Exception as e:
            try:
                db.session.rollback()
            except Exception:
                pass
            current_app.logger.error(f"Error in before_request: {e}")

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
    current_app.logger.info(f"User {current_user.id} accessing profile page")
    mistake_count = Mistake.query.filter_by(user_id=current_user.id, is_resolved=False).count()
    return render_template('profile.html', title='個人檔案', mistake_count=mistake_count)

@main.route("/chat")
@login_required
def chat():
    return render_template('chat.html', title='AI 聊天室')

@main.route("/update_profile", methods=['POST'])
@login_required
def update_profile():

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


@main.route("/change_password", methods=['POST'])
@login_required
def change_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    # Validate current password
    if not bcrypt.check_password_hash(current_user.password, current_password):
        flash('目前密碼不正確，請重新輸入。', 'danger')
        return redirect(url_for('main.profile'))

    # Validate new password
    if len(new_password) < 6:
        flash('新密碼至少需要 6 個字元。', 'danger')
        return redirect(url_for('main.profile'))

    if new_password != confirm_password:
        flash('兩次輸入的新密碼不一致，請重新輸入。', 'danger')
        return redirect(url_for('main.profile'))

    # Update password
    try:
        current_user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        db.session.commit()
        flash('密碼已成功變更！', 'success')
    except Exception:
        db.session.rollback()
        flash('密碼變更失敗，請稍後再試。', 'danger')

    return redirect(url_for('main.profile'))
