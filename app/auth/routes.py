from flask import Blueprint, render_template, url_for, flash, redirect, request, current_app
from flask_login import login_user, current_user, logout_user, login_required
import os
import secrets

auth = Blueprint('auth', __name__)

@auth.before_app_first_request
def setup_oauth():
    # OAuth configuration can happen inside a setup function or lazily
    pass

def get_google_client():
    from app import oauth
    return oauth.register(
        name='google',
        client_id=os.environ.get('GOOGLE_CLIENT_ID', ''),
        client_secret=os.environ.get('GOOGLE_CLIENT_SECRET', ''),
        server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
        client_kwargs={'scope': 'openid email profile'}
    )

@auth.route("/register", methods=['GET', 'POST'])
def register():
    from app import db, bcrypt
    from app.auth.forms import RegistrationForm
    from app.models import User
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_password)
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
        user = User.query.filter_by(email=form.email.data).first()
叠
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            current_app.logger.info(f"User {user.username} logged in successfully")
            if user.role == 'admin':
                flash(f'歡迎回來，{user.username} 👑 管理員！', 'admin-gold')
            else:
                flash(f'歡迎回來，{user.username}！', 'success')
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
        
        user = User.query.filter_by(email=email).first()
        
        is_admin = (email == 'ree84375@gmail.com')
        assigned_role = 'admin' if is_admin else 'student'
        
        if not user:
            random_password = bcrypt.generate_password_hash(secrets.token_hex(16)).decode('utf-8')
            # auth_provider and role upgrade logic temporarily simplified
            user = User(username=name, email=email, password=random_password, role=assigned_role)
            db.session.add(user)
            db.session.commit()
            flash('成功透過 Google 註冊並登入系統！', 'success')
        else:
            # Upgrade to admin if necessary
            if is_admin and user.role != 'admin':
                user.role = 'admin'
                db.session.commit()
            if user.role == 'admin':
                flash(f'歡迎回來，{user.username} 👑 管理員！', 'admin-gold')
            else:
                flash(f'歡迎回來，{user.username}！', 'success')
            
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
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    import random
    import string
    random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
    guest_username = f"訪客_{random_suffix}"
    
    hashed_pw = bcrypt.generate_password_hash('guestpassword').decode('utf-8')
    # auth_provider temporarily disabled
    user = User(username=guest_username, email=f"{guest_username}@guest.local", password=hashed_pw, role='guest')
    db.session.add(user)
    db.session.commit()
    
    login_user(user)
    flash(f'已使用訪客身分 ({guest_username}) 登入！', 'info')
    return redirect(url_for('main.home'))
