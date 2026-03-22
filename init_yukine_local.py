import os
# Force SQLite before importing app
os.environ['DATABASE_URL'] = '' 

from app import create_app, db, bcrypt
from app.models import User, Group, GroupMessage

def initialize_yukine():
    app = create_app()
    with app.app_context():
        print(f"Active DB: {app.config['SQLALCHEMY_DATABASE_URI']}")
        
        # Ensure all tables exist
        print("Ensuring all tables exist...")
        db.create_all()
        
        # Check for Yukine user
        yukine_username = '雪音老師'
        yukine = User.query.filter_by(username=yukine_username).first()
        
        if not yukine:
            print(f"Creating AI user: {yukine_username}...")
            hashed_pw = bcrypt.generate_password_hash('yukine_secure_pw_123').decode('utf-8')
            yukine = User(
                username=yukine_username,
                email='yukine@antigravity.ai',
                password=hashed_pw,
                role='teacher',
                ai_personality='雪音-溫柔型',
                language='zh'
            )
            db.session.add(yukine)
            try:
                db.session.commit()
                print(f"Successfully created {yukine_username} (ID: {yukine.id})")
            except Exception as e:
                db.session.rollback()
                print(f"Error creating Yukine: {e}")
        else:
            print(f"AI user {yukine_username} already exists (ID: {yukine.id})")

        # Enable AI for all groups
        groups = Group.query.all()
        for g in groups:
            if not g.has_ai:
                g.has_ai = True
                print(f"Enabled AI for group: {g.name} (ID: {g.id})")
        
        db.session.commit()
        print("Initialization complete.")

if __name__ == "__main__":
    initialize_yukine()
