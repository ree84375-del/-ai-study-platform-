from app import create_app, db
from sqlalchemy import text, inspect

app = create_app()

with app.app_context():
    try:
        inspector = inspect(db.engine)
        columns = [c['name'] for c in inspector.get_columns('chat_message')]
        print(f"Current columns in 'chat_message': {columns}")
        if 'image_data' in columns:
            print("VERIFIED: Column 'image_data' exists.")
        else:
            print("FAILED: Column 'image_data' missing!")
    except Exception as e:
        print(f"Error: {e}")
