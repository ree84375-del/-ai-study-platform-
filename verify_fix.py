import os
os.environ['DATABASE_URL'] = '' # Force SQLite

from app import create_app, db
from app.models import User, Group, GroupMessage
from datetime import datetime

def verify():
    app = create_app()
    with app.app_context():
        # 1. Check User
        yukine = User.query.filter_by(username='雪音老師').first()
        if yukine:
            print(f"✓ AI user '雪音老師' found (ID: {yukine.id}, Role: {yukine.role})")
        else:
            print("✗ AI user '雪音老師' NOT FOUND")
            
        # 2. Check Table columns
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        columns = [c['name'] for c in inspector.get_columns('user')]
        if 'ai_personality' in columns:
            print("✓ Column 'ai_personality' exists in 'user' table")
        else:
            print("✗ Column 'ai_personality' MISSING in 'user' table")
            
        if 'group_message' in inspector.get_table_names():
            print("✓ Table 'group_message' exists")
        else:
            print("✗ Table 'group_message' MISSING")

        # 3. Check Groups
        group = Group.query.first()
        if group:
            print(f"✓ Found group '{group.name}' (AI enabled: {group.has_ai})")
        else:
            print("! No groups found in database.")

        print("Verification complete.")

if __name__ == "__main__":
    verify()
