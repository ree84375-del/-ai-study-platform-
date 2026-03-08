from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from app import db
from datetime import datetime, timezone

main = Blueprint('main', __name__)

@main.before_app_request
def before_request():
    if current_user.is_authenticated:
        current_user.last_active_at = datetime.now(timezone.utc)
        db.session.commit()

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
