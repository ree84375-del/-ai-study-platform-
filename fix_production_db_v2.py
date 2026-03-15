from sqlalchemy import create_all, create_engine, text
import os

# Database connection URL from .env
db_url = "postgresql://postgres:rex11255203@db.nphrkuzhedlvgfagaujq.supabase.co:5432/postgres"

def fix_schema():
    print(f"Connecting to database via SQLAlchemy: {db_url}")
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            # PostgreSQL requires explicit commit if not in autocommit mode, 
            # or we can use the connection's execution
            
            print("Checking and adding columns to 'assignment' table...")
            conn.execute(text("ALTER TABLE assignment ADD COLUMN IF NOT EXISTS question_image VARCHAR(255);"))
            conn.execute(text("ALTER TABLE assignment ADD COLUMN IF NOT EXISTS reference_answer TEXT;"))
            conn.execute(text("ALTER TABLE assignment ADD COLUMN IF NOT EXISTS reference_image VARCHAR(255);"))

            print("Checking and adding columns to 'assignment_status' table...")
            conn.execute(text("ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS ai_explanation TEXT;"))
            conn.execute(text("ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS recognized_content TEXT;"))
            
            print("Committing changes...")
            conn.commit()

        print("Migration completed successfully!")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_schema()
