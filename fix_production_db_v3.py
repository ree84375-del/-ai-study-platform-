import psycopg2
import os
from dotenv import load_dotenv

# Load connection string from .env
load_dotenv()
db_url = os.getenv("DATABASE_URL")

def fix_ip_category():
    if not db_url:
        print("Error: DATABASE_URL not found in .env")
        return

    print(f"Connecting to production database...")
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()

        print("Checking and adding 'category' column to 'ip_access_log' table...")
        # Add category column if it doesn't exist
        cur.execute("ALTER TABLE ip_access_log ADD COLUMN IF NOT EXISTS category VARCHAR(20) DEFAULT 'unknown';")

        print("Migration completed successfully!")
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Migration Error: {e}")

if __name__ == "__main__":
    fix_ip_category()
