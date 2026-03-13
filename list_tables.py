from app import create_app, db
from sqlalchemy import inspect
import logging

logging.getLogger('sqlalchemy').setLevel(logging.ERROR)

app = create_app()
with app.app_context():
    print("Listing all tables in the database...")
    try:
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"Tables: {', '.join(tables)}")
    except Exception as e:
        print(f"Error listing tables: {e}")
