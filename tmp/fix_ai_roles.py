
import os
import sys
# Ensure app module can be found
sys.path.append(os.getcwd())

from app import create_app, db
from app.models import User

app = create_app()
with app.app_context():
    try:
        # Identify AI accounts by email domain
        ai_users = User.query.filter(User.email.like('%@internal.ai')).all()
        count = 0
        for u in ai_users:
            if u.role != 'teacher':
                print(f"Updating {u.username} ({u.email}): {u.role} -> teacher")
                u.role = 'teacher'
                count += 1
        
        if count > 0:
            db.session.commit()
            print(f"Successfully updated {count} AI accounts.")
        else:
            print("All AI accounts are already correctly assigned.")
    except Exception as e:
        db.session.rollback()
        print(f"Error during migration: {e}")
