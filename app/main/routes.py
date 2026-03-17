from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from datetime import datetime, timezone, timedelta
from app.utils.i18n import get_text as _t, TRANSLATIONS
import re

main = Blueprint('main', __name__)

@main.route("/ping")
def ping():
    return jsonify({"status": "ok", "message": "Backend is alive!"})

@main.before_app_request
def before_request():
    from app import db
    from app.models import User
    if current_user.is_authenticated:
        try:
            # Temporarily disabled until DB column 'last_active_at' is added
            pass
            # now = datetime.now(timezone.utc)
            # if getattr(current_user, 'last_active_at', None) is None or \
            #    (now - current_user.last_active_at).total_seconds() > 60:
            #     db.session.execute(
            #         db.update(User).where(User.id == current_user.id).values(
            #             last_active_at=now
            #         )
            #     )
            #     db.session.commit()
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
    study_plan = []
    
    if current_user.is_authenticated:
        # Taiwan is UTC+8
        tw_tz = timezone(timedelta(hours=8))
        today = datetime.now(tw_tz).date()
        today_omikuji = Omikuji.query.filter_by(user_id=current_user.id, drawn_date=today).first()
        recent_emas = Ema.query.filter_by(is_public=True).order_by(Ema.created_at.desc()).limit(10).all()
        # Find the most recent uncompleted Daruma, or the most recent completed one
        active_daruma = Daruma.query.filter_by(user_id=current_user.id, is_completed=False).order_by(Daruma.created_at.desc()).first()
        if not active_daruma:
            active_daruma = Daruma.query.filter_by(user_id=current_user.id, is_completed=True).order_by(Daruma.completed_at.desc()).first()

    # --- GLOBAL DATABASE HEALTH CHECK (Auto-Migration) ---
    from sqlalchemy import text
    from sqlalchemy.exc import ProgrammingError
    from app import db
    
    # Fix 1: GlobalStat table
    try:
        db.session.execute(text("SELECT 1 FROM global_stat LIMIT 1"))
    except ProgrammingError:
        db.session.rollback()
        current_app.logger.warning("Creating global_stat table...")
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS global_stat (
                id SERIAL PRIMARY KEY,
                zen_xp INTEGER DEFAULT 0,
                garden_level INTEGER DEFAULT 1,
                last_weather_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                current_weather VARCHAR(50) DEFAULT 'weather_fair',
                active_users_count INTEGER DEFAULT 0
            )
        """))
        db.session.commit()

    # Fix 2: User table columns
    try:
        db.session.execute(text("SELECT last_login FROM \"user\" LIMIT 1"))
    except ProgrammingError:
        db.session.rollback()
        current_app.logger.warning("Adding last_login to User table...")
        try:
            db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            db.session.commit()
        except Exception: db.session.rollback()

    # Fix 3: Language preference column
    try:
        db.session.execute(text("SELECT language FROM \"user\" LIMIT 1"))
    except ProgrammingError:
        db.session.rollback()
        current_app.logger.warning("Adding language to User table...")
        try:
            db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS language VARCHAR(5) DEFAULT 'zh'"))
            db.session.commit()
        except Exception: db.session.rollback()

    # --- END HEALTH CHECK ---

    # Collaborative Garden Stats logic
    try:
        from app.utils.garden_helpers import update_garden_state
        garden_stats = update_garden_state()
    except Exception as e:
        current_app.logger.error(f"Garden state error: {e}")
        # Fallback stats object
        class FallbackStats:
            zen_xp = 0
            garden_level = 1
            current_weather = 'weather_misty'
            active_users_count = 1
        garden_stats = FallbackStats()
            
    mistakes_to_review = 0
    if current_user.is_authenticated:
        from app.models import Mistake
        mistakes_to_review = Mistake.query.filter_by(user_id=current_user.id, is_resolved=False).count()
    
    # Roadmap data
    study_plan = None
    if current_user.is_authenticated:
        from urllib.parse import unquote
        if hasattr(current_user, 'study_roadmap') and current_user.study_roadmap:
            import json
            try:
                study_plan = json.loads(unquote(current_user.study_roadmap))
            except Exception:
                pass

    # If NOT authenticated or fallback
    if 'garden_stats' not in locals():
        from app.models import GlobalStat
        garden_stats = GlobalStat.get_instance()
    
    return render_template('home.html', 
                           announcements=announcements, 
                           today_omikuji=today_omikuji,
                           recent_emas=recent_emas,
                           active_daruma=active_daruma,
                           mistakes_to_review=mistakes_to_review,
                           study_plan=study_plan,
                           garden_stats=garden_stats)

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
    from app import db
    if not current_user.has_seen_tour:
        current_user.has_seen_tour = True
        db.session.commit()
    return jsonify({"status": "success"})

@main.route("/profile")
@login_required
def profile():
    from app.models import Mistake
    from app import db
    
    # Data Healing: If user is from Google domain but provider is 'local', heal it.
    if getattr(current_user, 'auth_provider', 'local') == 'local':
        if current_user.email.endswith('@chhs.tp.edu.tw') or current_user.email.endswith('@gmail.com'):
            current_user.auth_provider = 'google'
            db.session.commit()
            current_app.logger.info(f"Healed auth_provider for user {current_user.id}")

    current_app.logger.info(f"User {current_user.id} accessing profile page")
    mistake_count = Mistake.query.filter_by(user_id=current_user.id, is_resolved=False).count()
    return render_template('profile.html', title=_t('profile_title', current_user.language), mistake_count=mistake_count)

@main.route("/chat")
@login_required
def chat():
    return render_template('chat.html', title=_t('nav_chat', current_user.language))

@main.route("/update_profile", methods=['POST'])
@login_required
def update_profile():
    from app import db
    from app.models import User
    new_username = request.form.get('username', current_user.username)

    if new_username != current_user.username:
        # 1. Admin cannot change their name
        if current_user.is_admin:
            flash(_t('msg_admin_name_locked', current_user.language), 'warning')
            return redirect(url_for('main.profile'))
            
        # 2. Check forbidden names
        if User.is_name_forbidden(new_username):
            flash(_t('msg_forbidden_name', current_user.language), 'danger')
            return redirect(url_for('main.profile'))

        # 3. Check for duplicates
        existing_user = User.query.filter_by(username=new_username).first()
        if existing_user:
            flash(_t('msg_username_taken', current_user.language), 'danger')
            return redirect(url_for('main.profile'))

    current_user.username = new_username
    
    # Safe updates for columns that might be disabled
    for attr in ['bio', 'learning_goals', 'ai_personality', 'preferred_theme', 'avatar_url', 'language']:
        if hasattr(current_user, attr):
            new_val = request.form.get(attr)
            if new_val is not None:
                setattr(current_user, attr, new_val)

    try:
        from flask import session
        if hasattr(current_user, 'language'):
            session['language'] = current_user.language
        db.session.commit()
        flash(_t('msg_profile_updated', current_user.language), 'success')
    except Exception:
        db.session.rollback()
        flash(_t('msg_update_failed', current_user.language), 'danger')

    return redirect(url_for('main.profile'))


@main.route("/set_language/<lang>")
def set_language(lang):
    if lang not in ['zh', 'ja', 'en']:
        lang = 'zh'
    
    from flask import session
    session['language'] = lang
    
    if current_user.is_authenticated:
        from app import db
        current_user.language = lang
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            
    # Try to redirect to the previous page
    next_page = request.args.get('next') or request.referrer
    if not next_page or '/set_language' in next_page:
        next_page = url_for('main.home')
    
    return redirect(next_page)


@main.route("/change_password", methods=['POST'])
@login_required
def change_password():
    from app import db, bcrypt
    # Google/Third-party users cannot change password here
    if getattr(current_user, 'auth_provider', 'local') not in ['local', 'guest']:
        flash(_t('go_to_google', current_user.language), 'info')
        return redirect(url_for('main.profile'))

    # Cooldown check (Temporarily disabled due to DB migration issue)
    # TODO: Re-enable after verified migration

    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    # Validate current password
    if not bcrypt.check_password_hash(current_user.password, current_password):
        flash(_t('msg_current_pwd_wrong', current_user.language), 'danger')
        return redirect(url_for('main.profile'))

    # Validate new password
    if len(new_password) < 6:
        flash(_t('msg_new_pwd_too_short', current_user.language), 'danger')
        return redirect(url_for('main.profile'))

    if new_password != confirm_password:
        flash(_t('msg_pwd_mismatch', current_user.language), 'danger')
        return redirect(url_for('main.profile'))

    # Update password
    try:
        current_user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
        db.session.commit()
        flash(_t('msg_pwd_changed', current_user.language), 'success')
    except Exception:
        db.session.rollback()
        flash(_t('msg_pwd_change_failed', current_user.language), 'danger')

    return redirect(url_for('main.profile'))

# --- Japanese-Themed Home Page Features ---

@main.route("/api/omikuji/draw", methods=['POST'])
@login_required
def draw_omikuji():
    from app import db
    from app.models import Omikuji
    from app.utils.ai_helpers import get_gemini_model
    import random
    import json
    from datetime import timedelta
    
    # Taiwan is UTC+8
    tw_tz = timezone(timedelta(hours=8))
    today = datetime.now(tw_tz).date()
    lang = getattr(current_user, 'language', 'zh')

    # Check if already drawn today
    existing = Omikuji.query.filter_by(user_id=current_user.id, drawn_date=today).first()
    if existing:
        flash(_t('omikuji_already_drawn', lang), 'info')
        return redirect(url_for('main.home'))
        
    fortunes = ['大吉', '吉', '吉', '中吉', '小吉', '末吉'] # Adjusted probabilities
    drawn_fortune = random.choice(fortunes)
    
    lang = getattr(current_user, 'language', 'zh')
    translated_fortune_label = _t(f'fortune_{drawn_fortune}', lang)
    
    try:
        # Prompt generation based on language
        if lang == 'ja':
            prompt = _t('prompt_omikuji_ja', lang=lang, fortune_label=translated_fortune_label, fortune_level=drawn_fortune)
        elif lang == 'en':
            prompt = _t('prompt_omikuji_en', lang=lang, fortune_label=translated_fortune_label, fortune_level=drawn_fortune)
        else: # zh or default
            prompt = _t('prompt_omikuji_zh', lang=lang, fortune_label=translated_fortune_label, fortune_level=drawn_fortune)
        
        from app.utils.ai_helpers import generate_text_with_fallback
        text = generate_text_with_fallback(prompt).strip()
        if '```' in text:
            # Handle markdown blocks more robustly
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
            if match:
                text = match.group(1)
            else:
                text = text.replace('```json', '').replace('```', '')
        data = json.loads(text)

        
        # Store raw JSON data in the message field for frontend localization
        omikuji_data = {
            'lucky_color': data.get('lucky_color', '...'),
            'lucky_item': data.get('lucky_item', '...'),
            'lucky_subject': data.get('lucky_subject', '...'),
            'advice': data.get('advice', '...')
        }
        
        omikuji = Omikuji(user_id=current_user.id, fortune_level=drawn_fortune, message=json.dumps(omikuji_data), drawn_date=today)
        db.session.add(omikuji)
        
        # Add Garden XP (Drawing fortune: 5 XP)
        from app.utils.garden_helpers import add_garden_xp
        add_garden_xp(5)
        
        db.session.commit()
        db.session.commit()
        
        flash(_t('omikuji_draw_success', lang, fortune=_t(f'fortune_{drawn_fortune}', lang)), 'success')
        return redirect(url_for('main.home'))
    except Exception as e:
        db.session.rollback()
        error_msg = str(e)
        current_app.logger.error(f"Omikuji Error: {error_msg}")
        
        # provide a more helpful message if it's an AI fallback failure
        if "AI 模型" in error_msg or "API Key" in error_msg:
            flash(_t('msg_god_busy', lang).format(error=error_msg), 'danger')
        else:
            flash(_t('msg_god_error', lang).format(error=error_msg), 'warning')
        return redirect(url_for('main.home'))

@main.route("/api/ema/create", methods=['POST'])
@login_required
def create_ema():
    from app import db
    from app.models import Ema
    content = request.form.get('content')
    is_public = request.form.get('is_public') == 'true'
    
    if not content or len(content) > 100:
        flash(_t('msg_ema_empty', current_user.language), 'danger')
        return redirect(url_for('main.home'))
        
    ema = Ema(user_id=current_user.id, content=content, is_public=is_public)
    db.session.add(ema)
    
    # Add Garden XP (Creating Ema: 10 XP)
    from app.utils.garden_helpers import add_garden_xp
    add_garden_xp(10)
    
    db.session.commit()
    flash(_t('msg_ema_success', current_user.language), 'success')
    return redirect(url_for('main.home'))

@main.route("/api/daruma/create", methods=['POST'])
@login_required
def create_daruma():
    from app import db
    from app.models import Daruma
    goal = request.form.get('goal')
    
    if not goal or len(goal) > 100:
        flash(_t('msg_daruma_empty', current_user.language), 'danger')
        return redirect(url_for('main.home'))
        
    daruma = Daruma(user_id=current_user.id, goal=goal)
    db.session.add(daruma)
    db.session.commit()
    flash(_t('msg_daruma_success', current_user.language), 'success')
    return redirect(url_for('main.home'))

@main.route("/api/toggle_dark_mode", methods=['POST'])
@login_required
def toggle_dark_mode():
    from app import db
    if not hasattr(current_user, 'preferred_theme'):
        return jsonify({"status": "error", "message": "Theme setting not available"}), 400
        
    if current_user.preferred_theme == 'midnight':
        current_user.preferred_theme = 'sakura' 
    else:
        current_user.preferred_theme = 'midnight'
    
    try:
        db.session.commit()
        return jsonify({"status": "success", "new_theme": current_user.preferred_theme})
    except Exception:
        db.session.rollback()
        return jsonify({"status": "error"}), 500

@main.route("/api/daruma/<int:daruma_id>/complete", methods=['POST'])
@login_required
def complete_daruma(daruma_id):
    from app import db
    from app.models import Daruma
    daruma = Daruma.query.get_or_404(daruma_id)
    if daruma.user_id != current_user.id:
        flash(_t('msg_unauthorized', current_user.language), 'danger')
        return redirect(url_for('main.home'))
        
    if daruma.is_completed:
        flash(_t('msg_daruma_already_done', current_user.language), 'info')
        return redirect(url_for('main.home'))
        
    daruma.is_completed = True
    daruma.completed_at = datetime.now(timezone.utc)
    
    # Add Garden XP (Completing Daruma: 30 XP)
    from app.utils.garden_helpers import add_garden_xp
    add_garden_xp(30)
    
    db.session.commit()
    flash(_t('msg_daruma_complete_success', current_user.language), 'success')
    return redirect(url_for('main.home'))

@main.route("/api/update_theme", methods=['POST'])
@login_required
def update_theme():
    from app import db
    data = request.get_json()
    if not data or 'theme' not in data:
        return jsonify({"status": "error", "message": "Invalid data"}), 400
    
    theme = data.get('theme')
    if hasattr(current_user, 'preferred_theme'):
        current_user.preferred_theme = theme
        try:
            db.session.commit()
            return jsonify({"status": "success"})
        except Exception:
            db.session.rollback()
            return jsonify({"status": "error"}), 500
    return jsonify({"status": "skipped", "message": "Field not in DB"}), 200

@main.route("/debug/setup_db")
@login_required
def setup_db():
    from app import db
    from sqlalchemy import text
    if not current_user.is_admin:
        return "Unauthorized", 403
        
    messages = []
    try:
        db.create_all()
        messages.append("db.create_all() successful.")
        
        migration_statements = [
            "ALTER TABLE \"group\" ADD COLUMN IF NOT EXISTS has_ai BOOLEAN DEFAULT TRUE",
            "ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS content TEXT",
            "ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS ai_feedback TEXT",
            "ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS score INTEGER",
            "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS exam_date DATE",
            "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS study_plan_json TEXT",
            "ALTER TABLE \"group\" ADD COLUMN IF NOT EXISTS garden_exp INTEGER DEFAULT 0",
            "ALTER TABLE \"group\" ADD COLUMN IF NOT EXISTS garden_level INTEGER DEFAULT 1",
            "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS bio TEXT",
            "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS learning_goals TEXT",
            "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS ai_personality VARCHAR(50) DEFAULT '雪音-溫柔型'",
            "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(255)",
            "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(20) DEFAULT 'local'",
            "ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP",
            "ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS is_completed BOOLEAN DEFAULT FALSE",
            "ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP",
            "ALTER TABLE assignment ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS image_data TEXT",
            "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS parent_id INTEGER REFERENCES group_message(id)",
            "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS is_edited BOOLEAN DEFAULT FALSE",
            "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS is_recalled BOOLEAN DEFAULT FALSE",
            "ALTER TABLE group_message ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE"
        ]
        
        for stmt in migration_statements:
            try:
                db.session.execute(text(stmt))
                db.session.commit()
                messages.append(f"Executed: {stmt[:40]}...")
            except Exception as e:
                db.session.rollback()
                messages.append(f"Skipped/Error: {stmt[:40]}... ({str(e)})")
        
        return f"<h3>Database Setup Complete</h3><pre>" + "\n".join(messages) + "</pre>"
    except Exception as e:
        return f"<h3>Database Setup FAILED</h3><pre>{str(e)}</pre>", 500

@main.route("/debug/fix_group_db")
@login_required
def fix_group_db():
    from app import db
    if not current_user.is_admin:
        return "Unauthorized", 403
    from sqlalchemy import text
    try:
        # Check if table is "group" or "groups"
        db.session.execute(text("ALTER TABLE \"group\" ADD COLUMN IF NOT EXISTS has_ai BOOLEAN DEFAULT TRUE;"))
        db.session.commit()
        return "SUCCESS: Column 'has_ai' added to table 'group'. <a href='/groups'>Back to Groups</a>", 200
    except Exception as e:
        db.session.rollback()
        return f"ERROR: {str(e)}", 500
