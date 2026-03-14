from app import create_app, db
from sqlalchemy import inspect

app = create_app()
with app.app_context():
    inspector = inspect(db.engine)
    
    print("User table columns:")
    for column in inspector.get_columns('user'):
        print(f" - {column['name']}")
        
    print("\nGroup table columns:")
    for column in inspector.get_columns('group'):
        print(f" - {column['name']}")
