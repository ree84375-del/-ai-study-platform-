import sqlite3

db_path = "c:/Users/Good PC/.gemini/antigravity/scratch/ai_study_platform/instance/site.db"

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if column exists
    cursor.execute("PRAGMA table_info(chat_message)")
    columns = [info[1] for info in cursor.fetchall()]
    
    if 'image_data' not in columns:
        print("Column 'image_data' missing in local SQLite. Adding it now...")
        cursor.execute("ALTER TABLE chat_message ADD COLUMN image_data TEXT")
        conn.commit()
        print("Successfully added 'image_data' to site.db")
    else:
        print("Column 'image_data' already exists in local site.db")
        
    conn.close()
except Exception as e:
    print(f"Error modifying site.db: {e}")
