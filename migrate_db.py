import os
from sqlalchemy import text, create_engine
from dotenv import load_dotenv

load_dotenv()

def migrate():
    db_uri = os.environ.get('DATABASE_URL')
    if not db_uri:
        print("No DATABASE_URL found.")
        return
    
    if db_uri.startswith("postgres://"):
        db_uri = db_uri.replace("postgres://", "postgresql://", 1)
        
    engine = create_engine(db_uri)
    
    with engine.connect() as conn:
        print("Checking for 'language' column in 'user' table...")
        try:
            # PostgreSQL syntax to add column if not exists
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS language VARCHAR(5) DEFAULT 'zh'"))
            conn.commit()
            print("Successfully added 'language' column (or it already existed).")
        except Exception as e:
            print(f"Error during migration: {e}")
            
        print("Checking for 'last_login' column...")
        try:
            conn.execute(text("ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            conn.commit()
            print("Successfully added 'last_login' column.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    migrate()
