import sqlite3
import os

def migrate():
    db_path = 'instance/site.db'
    if not os.path.exists(db_path):
        print("Database not found at instance/site.db")
        return

    print(f"Using database at: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        print("Adding 'category' column to 'ip_access_log' table...")
        cursor.execute("ALTER TABLE ip_access_log ADD COLUMN category VARCHAR(20) DEFAULT 'unknown'")
        conn.commit()
        print("Migration successful.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("Column 'category' already exists.")
        else:
            print(f"Migration error: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
