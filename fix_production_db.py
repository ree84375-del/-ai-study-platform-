import psycopg2
import os

# Database connection URL from .env
db_url = "postgresql://postgres:rex11255203@db.nphrkuzhedlvgfagaujq.supabase.co:5432/postgres"

def fix_schema():
    print(f"Connecting to database: {db_url}")
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()

        print("Checking and adding columns to 'assignment' table...")
        # Add question_image
        cur.execute("ALTER TABLE assignment ADD COLUMN IF NOT EXISTS question_image VARCHAR(255);")
        # Add reference_answer and reference_image just in case they are missing
        cur.execute("ALTER TABLE assignment ADD COLUMN IF NOT EXISTS reference_answer TEXT;")
        cur.execute("ALTER TABLE assignment ADD COLUMN IF NOT EXISTS reference_image VARCHAR(255);")

        print("Checking and adding columns to 'assignment_status' table...")
        # Add ai_explanation and recognized_content
        cur.execute("ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS ai_explanation TEXT;")
        cur.execute("ALTER TABLE assignment_status ADD COLUMN IF NOT EXISTS recognized_content TEXT;")

        print("Migration completed successfully!")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    fix_schema()
