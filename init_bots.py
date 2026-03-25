import os
import sys
from datetime import datetime, timezone

# Add the project root to sys.path
sys.path.append(r'c:\Users\Good PC\ .gemini\antigravity\scratch\ai_study_platform')

try:
    from app import db, create_app, bcrypt
    from app.models import User
except ImportError:
    # If standard import fails, try relative or absolute with context
    print("Import failed, attempting with app context manually...")
    sys.path.append(os.getcwd())
    from app import db, create_app, bcrypt
    from app.models import User

app = create_app()

def init_bots():
    with app.app_context():
        bots = [
            {
                'email': 'yukine_bot@internal.ai',
                'username': '雪音 (Antigravity 核心)',
                'personality': '雪音-溫柔型',
                'role': 'teacher'
            },
            {
                'email': 'senior_bot@internal.ai',
                'username': '學長 (Antigravity 核心)',
                'personality': 'ai_guy',
                'role': 'teacher'
            },
            {
                'email': 'coach_bot@internal.ai',
                'username': '教練 (Antigravity 核心)',
                'personality': 'ai_coach',
                'role': 'teacher'
            }
        ]
        
        for bot_data in bots:
            user = User.query.filter_by(email=bot_data['email']).first()
            if not user:
                print(f"Creating bot: {bot_data['username']} ({bot_data['email']})")
                hashed_password = bcrypt.generate_password_hash('antigravity_core_v1').decode('utf-8')
                user = User(
                    username=bot_data['username'],
                    email=bot_data['email'],
                    password=hashed_password,
                    role=bot_data['role'],
                    ai_personality=bot_data['personality']
                )
                db.session.add(user)
            else:
                print(f"Bot already exists: {bot_data['username']} ({bot_data['email']})")
                user.username = bot_data['username'] # Update name if needed
                user.ai_personality = bot_data['personality']
                user.role = bot_data['role']
        
        # Also handle the legacy/alt email from code: yukine_bot_ag@internal.ai
        alt_email = 'yukine_bot_ag@internal.ai'
        alt_user = User.query.filter_by(email=alt_email).first()
        if alt_user:
             print(f"Updating alt bot: {alt_email}")
             alt_user.username = '雪音 (Antigravity 核心)'
             alt_user.ai_personality = '雪音-溫柔型'
        
        db.session.commit()
        print("Bot initialization complete.")

if __name__ == '__main__':
    init_bots()
