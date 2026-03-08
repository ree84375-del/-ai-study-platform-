from flask import Blueprint, render_template, url_for, flash, redirect, request
from app import db, bcrypt
from app.auth.forms import RegistrationForm, LoginForm
from app.models import User
from flask_login import login_user, current_user, logout_user, login_required

auth = Blueprint('auth', __name__)

@auth.route("/register", methods=['GET', 'POST'])
def register():
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
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.home'))
        else:
            flash('登入失敗。請檢查 Email 和密碼', 'danger')
    return render_template('login.html', title='登入', form=form)

@auth.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('main.home'))

@auth.route("/guest_login")
def guest_login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    import random
    import string
    random_suffix = ''.join(random.choices(string.ascii_letters + string.digits, k=5))
    guest_username = f"訪客_{random_suffix}"
    
    user = User(username=guest_username, email=f"{guest_username}@guest.local", password='guestpassword', role='guest')
    db.session.add(user)
    db.session.commit()
    
    login_user(user)
    flash(f'已使用訪客身分 ({guest_username}) 登入！', 'info')
    return redirect(url_for('main.home'))
