from app import create_app, db
from sqlalchemy import text
import logging

# Disable extra logging to keep output clean
logging.getLogger('sqlalchemy').setLevel(logging.ERROR)

app = create_app()
with app.app_context():
    print("Attempting to add 'has_ai' column within app context...")
    try:
        # Use quoted table name "group" as it is a reserved word
        db.session.execute(text("ALTER TABLE \"group\" ADD COLUMN IF NOT EXISTS has_ai BOOLEAN DEFAULT TRUE;"))
        db.session.commit()
        print("Successfully added 'has_ai' column (or it already exists).")
    except Exception as e:
        print(f"Error during migration: {e}")
        db.session.rollback()
