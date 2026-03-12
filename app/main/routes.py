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
            # Only update last_active_at once per minute to reduce DB writes
            now = datetime.now(timezone.utc)
            if current_user.last_active_at is None or \
               (now - current_user.last_active_at).total_seconds() > 60:
                db.session.execute(
                    db.update(User).where(User.id == current_user.id).values(
                        last_active_at=now
                    )
                )
                db.session.commit()
        except Exception:
            # Silently ignore — NEVER let a tracking update break the user session
            try:
                db.session.rollback()
            except Exception:
                pass

@main.route("/")
@main.route("/home")
def home():
    from app.models import Announcement, Omikuji, Ema, Daruma, Mistake
    # Fetch latest 3 announcements
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).limit(3).all()
    
    # Check Japanese Features if user is logged in
    today_omikuji = None
    recent_emas = []
    active_daruma = None
    mistakes_to_review = 0
    
    if current_user.is_authenticated:
        today = datetime.now(timezone.utc).date()
        today_omikuji = Omikuji.query.filter_by(user_id=current_user.id, drawn_date=today).first()
        recent_emas = Ema.query.filter_by(is_public=True).order_by(Ema.created_at.desc()).limit(10).all()
        # Find the most recent uncompleted Daruma, or the most recent completed one
        active_daruma = Daruma.query.filter_by(user_id=current_user.id, is_completed=False).order_by(Daruma.created_at.desc()).first()
        if not active_daruma:
            active_daruma = Daruma.query.filter_by(user_id=current_user.id, is_completed=True).order_by(Daruma.completed_at.desc()).first()
            
        mistakes_to_review = Mistake.query.filter_by(user_id=current_user.id, is_resolved=False).count()
        
    return render_template('home.html', 
                           announcements=announcements, 
                           today_omikuji=today_omikuji,
                           recent_emas=recent_emas,
                           active_daruma=active_daruma,
                           mistakes_to_review=mistakes_to_review)

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
    # Google/guest users cannot change password here
    if current_user.auth_provider in ('google', 'guest'):
        flash('此帳號類型無法在此變更密碼。', 'info')
        return redirect(url_for('main.profile'))

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

# --- Japanese-Themed Home Page Features ---

@main.route("/api/omikuji/draw", methods=['POST'])
@login_required
def draw_omikuji():
    from app.models import Omikuji
    from app.utils.ai_helpers import get_gemini_model
    import random
    import json
    
    today = datetime.now(timezone.utc).date()
    # Check if already drawn today
    existing = Omikuji.query.filter_by(user_id=current_user.id, drawn_date=today).first()
    if existing:
        flash('今天已經抽過御神籤了喔！', 'info')
        return redirect(url_for('main.home'))
        
    fortunes = ['大吉', '吉', '吉', '中吉', '小吉', '末吉'] # Adjusted probabilities
    drawn_fortune = random.choice(fortunes)
    
    try:
        prompt = f"學生抽到了「{drawn_fortune}」。請以溫柔的日式神職人員或巫女的語氣，為他寫一段大約 30 字的今日學習箴言。回傳 JSON 格式：{{\"message\": \"你的箴言\"}}。除了 JSON 之外不要有其他字。"
        from app.utils.ai_helpers import generate_text_with_fallback
        text = generate_text_with_fallback(prompt).strip()
        if text.startswith('```json'):
            text = text[7:]
        if text.endswith('```'):
            text = text[:-3]
        data = json.loads(text)
        message = data.get('message', '今天也是充滿希望的一天，跟著雪音一起努力吧！')
        
        omikuji = Omikuji(user_id=current_user.id, fortune_level=drawn_fortune, message=message, drawn_date=today)
        db.session.add(omikuji)
        db.session.commit()
        
        flash(f'抽到了【{drawn_fortune}】神籤！', 'success')
        return redirect(url_for('main.home'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Omikuji Error: {str(e)}")
        flash('神明目前太過忙碌 (API 呼叫次數達上限)，請稍後再試一次！', 'danger')
        return redirect(url_for('main.home'))

@main.route("/api/ema/create", methods=['POST'])
@login_required
def create_ema():
    from app.models import Ema
    content = request.form.get('content')
    is_public = request.form.get('is_public') == 'true'
    
    if not content or len(content) > 100:
        flash('繪馬內容不可空白或超過 100 字。', 'danger')
        return redirect(url_for('main.home'))
        
    ema = Ema(user_id=current_user.id, content=content, is_public=is_public)
    db.session.add(ema)
    db.session.commit()
    flash('祈願繪馬已掛上！', 'success')
    return redirect(url_for('main.home'))

@main.route("/api/daruma/create", methods=['POST'])
@login_required
def create_daruma():
    from app.models import Daruma
    goal = request.form.get('goal')
    
    if not goal or len(goal) > 100:
        flash('達磨目標不可空白或超過 100 字。', 'danger')
        return redirect(url_for('main.home'))
        
    daruma = Daruma(user_id=current_user.id, goal=goal)
    db.session.add(daruma)
    db.session.commit()
    flash('新的達磨不倒翁已為您準備好，請努力達成目標為它開眼！', 'success')
    return redirect(url_for('main.home'))

@main.route("/api/daruma/<int:daruma_id>/complete", methods=['POST'])
@login_required
def complete_daruma(daruma_id):
    from app.models import Daruma
    daruma = Daruma.query.get_or_404(daruma_id)
    if daruma.user_id != current_user.id:
        flash('權限不足', 'danger')
        return redirect(url_for('main.home'))
        
    if daruma.is_completed:
        flash('達磨已經開眼囉！', 'info')
        return redirect(url_for('main.home'))
        
    daruma.is_completed = True
    daruma.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    flash('恭喜達成目標！達磨已成功開眼。', 'success')
    return redirect(url_for('main.home'))
