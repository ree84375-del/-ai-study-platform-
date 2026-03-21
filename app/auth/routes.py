from flask import Blueprint, render_template, url_for, flash, redirect, request, current_app
from flask_login import login_user, current_user, logout_user, login_required
import os
import secrets
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from app.utils.i18n import get_text as _t

auth = Blueprint('auth', __name__)

# Google OAuth registration logic should be here or inside create_app
# But we'll use a lazily-initialized helper for maximum stability
_google_client = None

def get_google_client():
    global _google_client
    if _google_client: return _google_client
    
    from app import oauth
    _google_client = oauth.register(
        name='google',
        client_id=os.environ.get('GOOGLE_CLIENT_ID', ''),
        client_secret=os.environ.get('GOOGLE_CLIENT_SECRET', ''),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )
    return _google_client

def repair_database():
    from app import db
    current_app.logger.warning("Emergency: Database columns missing. Attempting auto-repair...")
    try:
        # Check and add 'language'
        db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS language VARCHAR(5) DEFAULT 'zh'"))
        # Check and add 'last_login'
        db.session.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
        db.session.commit()
        current_app.logger.info("Auto-repair: Missing columns added successfully.")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Auto-repair failed: {e}")

@auth.route("/register", methods=['GET', 'POST'])
def register():
    from app import db, bcrypt
    from app.auth.forms import RegistrationForm
    from app.models import User
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        if User.is_name_forbidden(form.username.data):
            flash('此名稱包含禁用關鍵字，請更換一個名稱。', 'danger')
            return render_template('register.html', title='註冊', form=form)
            
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
        db.session.add(user)
        user.last_login = datetime.now(timezone.utc)
        db.session.add(user)
        db.session.commit()
        flash('您的帳號已成功建立！現在可以登入了', 'success')
        return redirect(url_for('auth.login'))
    return render_template('register.html', title='註冊', form=form)

@auth.route("/login", methods=['GET', 'POST'])
def login():
    from app import bcrypt
    from app.auth.forms import LoginForm
    from app.models import User
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    form = LoginForm()
    if form.validate_on_submit():
        try:
            user = User.query.filter_by(email=form.email.data).first()
        except ProgrammingError:
            repair_database()
            user = User.query.filter_by(email=form.email.data).first()
        
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            # Force Admin name
            if user.role == 'admin' and user.username != '管理員':
                user.username = '管理員'
            
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            login_user(user, remember=form.remember.data)
            current_app.logger.info(f"User {user.username} logged in successfully")
            if user.role == 'admin':
                flash(_t('msg_admin_welcome', user.language).format(username=user.username), 'admin-gold')
            else:
                flash(_t('msg_user_welcome', user.language).format(username=user.username), 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.home'))
        else:
            flash('登入失敗。請檢查 Email 和密碼', 'danger')
    return render_template('login.html', title='登入', form=form)

@auth.route("/login/google")
def google_login():
    google = get_google_client()
    scheme = 'https' if os.environ.get('VERCEL') or request.headers.get('x-forwarded-proto') == 'https' else 'http'
    redirect_uri = url_for('auth.google_auth', _external=True, _scheme=scheme)
    return google.authorize_redirect(redirect_uri)

@auth.route('/auth/google/callback')
def google_auth():
    from app import db, bcrypt
    from app.models import User
    google = get_google_client()
    try:
        token = google.authorize_access_token()
        user_info = token.get('userinfo')
        
        if not user_info:
            flash('無法取得 Google 帳號資訊。', 'danger')
            return redirect(url_for('auth.login'))
            
        email = user_info.get('email')
        name = user_info.get('name')
        
        try:
            user = User.query.filter_by(email=email).first()
        except ProgrammingError:
            repair_database()
            user = User.query.filter_by(email=email).first()
        
        is_admin = (email == 'ree84375@gmail.com')
        assigned_role = 'admin' if is_admin else 'student'
        
        if not user:
            random_password = bcrypt.generate_password_hash(secrets.token_hex(16)).decode('utf-8')
            final_name = '管理員' if assigned_role == 'admin' else name
            user = User(username=final_name, email=email, password=random_password, role=assigned_role, auth_provider='google')
            db.session.add(user)
            db.session.commit()
            flash('成功透過 Google 註冊並登入系統！', 'success')
        else:
            # Healing/Upgrade logic: Ensure existing OAuth users are marked as Google
            if getattr(user, 'auth_provider', 'local') != 'google':
                user.auth_provider = 'google'
            
            # Upgrade to admin if necessary
            if is_admin and user.role != 'admin':
                user.role = 'admin'
            
            # Force Admin name
            if user.role == 'admin' and user.username != '管理員':
                user.username = '管理員'
            
            db.session.commit()
            if user.role == 'admin':
                flash(_t('msg_admin_welcome', user.language).format(username=user.username), 'admin-gold')
            else:
                flash(_t('msg_user_welcome', user.language).format(username=user.username), 'success')
            
        user.last_login = datetime.now(timezone.utc)
        db.session.commit()
        login_user(user)
        return redirect(url_for('main.home'))
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        flash(f'Google 登入失敗：{str(e)}', 'danger')
        # 暫時在頁面上顯示詳細錯誤以便除錯
        return f'<h3>Google OAuth 錯誤</h3><pre>{error_details}</pre><br><a href="/login">返回登入頁</a>', 500

@auth.route("/logout")
def logout():
    current_app.logger.info(f"User {getattr(current_user, 'username', 'anonymous')} logged out")
    logout_user()
    return redirect(url_for('main.home'))

@auth.route("/guest_login")
def guest_login():
    from app import db, bcrypt
    from app.models import User
    from flask import session
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    import random
    import string
    random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
    guest_username = f"訪客_{random_suffix}"
    
    guest_pw = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    hashed_pw = bcrypt.generate_password_hash(guest_pw).decode('utf-8')
    user = User(username=guest_username, email=f"{guest_username}@guest.local", password=hashed_pw, role='guest', auth_provider='guest')
    user.last_login = datetime.now(timezone.utc)
    db.session.add(user)
    db.session.commit()
    
    login_user(user)
    session['guest_pw'] = guest_pw
    
    flash(f'''已為您建立專屬訪客帳號！請務必記下以下登入資訊：
    <br><strong>帳號：</strong>{guest_username}
    <br><strong>密碼：</strong>{guest_pw}
    <hr style="margin:5px 0" />您可以隨時到「個人設定」將帳號轉正。''', 'warning')
    return redirect(url_for('main.home'))

@auth.route("/upgrade_guest", methods=["POST"])
@login_required
def upgrade_guest():
    from app import db, bcrypt
    from app.models import User
    if getattr(current_user, 'auth_provider', 'local') != 'guest':
        flash('只有訪客帳號可以升級！', 'danger')
        return redirect(url_for('main.profile'))
        
    new_email = request.form.get('new_email', '').strip()
    new_password = request.form.get('new_password', '')
    
    if len(new_password) < 6:
        flash('新密碼長度至少需要 6 分碼！', 'danger')
        return redirect(url_for('main.profile'))
        
    existing_user = User.query.filter_by(email=new_email).first()
    if existing_user:
        flash('該 Email 已被註冊（或是被您的 Google 登入帳號綁定）。', 'danger')
        return redirect(url_for('main.profile'))
        
    # Upgrade current user preserving ID and chat history
    current_user.email = new_email
    current_user.password = bcrypt.generate_password_hash(new_password).decode('utf-8')
    current_user.role = 'student'
    current_user.auth_provider = 'local'
    if current_user.username.startswith('訪客_'):
        current_user.username = current_user.username.replace('訪客_', '學員_')
        
    db.session.commit()
    flash('帳號已成功升級轉正！已為您保留原本訪客的所有對話與學習紀錄！', 'success')
    return redirect(url_for('main.profile'))
