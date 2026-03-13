import os
import psycopg2
from dotenv import load_dotenv

# Load .env from the parent directory where the script is usually run
load_dotenv(os.path.join(os.getcwd(), '.env'))

db_url = os.environ.get('DATABASE_URL')
if not db_url:
    print("DATABASE_URL not found in .env")
    exit(1)

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

print(f"Connecting to database...")
try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    print("Adding column 'has_ai' to table 'group'...")
    cur.execute("ALTER TABLE \"group\" ADD COLUMN IF NOT EXISTS has_ai BOOLEAN DEFAULT TRUE;")
    conn.commit()
    cur.close()
    conn.close()
    print("Column 'has_ai' added successfully or already exists.")
except Exception as e:
    print(f"An error occurred: {e}")
