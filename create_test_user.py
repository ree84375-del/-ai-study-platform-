from app import create_app, db, bcrypt
from app.models import User

app = create_app()

with app.app_context():
    email = "test@example.com"
    username = "測試員"
    password = "password123"
    
    existing = User.query.filter_by(email=email).first()
    if existing:
        print(f"User {email} already exists. Password might be different, but you can try 'password123' or use Google Login.")
    else:
        hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
        user = User(username=username, email=email, password=hashed_pw, role='student')
        db.session.add(user)
        db.session.commit()
        print(f"Created user: {email} / {password}")
