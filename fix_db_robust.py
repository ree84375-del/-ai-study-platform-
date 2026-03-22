import sqlite3
import os

def fix_db(db_path):
    if not os.path.exists(db_path):
        print(f"--- {db_path} NOT FOUND ---")
        return
    print(f"--- Fixing {db_path} ---")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    
    # 1. Add missing columns to user table
    try:
        c.execute("PRAGMA table_info(user)")
        cols = [col[1] for col in c.fetchall()]
        if 'ai_personality' not in cols:
            print("Adding ai_personality to user...")
            c.execute("ALTER TABLE user ADD COLUMN ai_personality VARCHAR(50) DEFAULT '雪音-溫柔型'")
        if 'language' not in cols:
            print("Adding language to user...")
            c.execute("ALTER TABLE user ADD COLUMN language VARCHAR(5) DEFAULT 'zh'")
    except Exception as e:
        print(f"Error updating user table: {e}")

    # 2. Create group_message table if missing
    try:
        c.execute('''
        CREATE TABLE IF NOT EXISTS group_message (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            image_data TEXT,
            created_at DATETIME,
            parent_id INTEGER,
            is_edited BOOLEAN DEFAULT 0,
            is_recalled BOOLEAN DEFAULT 0,
            is_deleted BOOLEAN DEFAULT 0,
            FOREIGN KEY(group_id) REFERENCES "group"(id),
            FOREIGN KEY(user_id) REFERENCES "user"(id),
            FOREIGN KEY(parent_id) REFERENCES group_message(id)
        )
        ''')
        print("Ensured group_message table exists.")
    except Exception as e:
        print(f"Error creating group_message table: {e}")

    # 3. Create Yukine user
    try:
        c.execute("SELECT id FROM user WHERE username = '雪音老師'")
        if not c.fetchone():
            print("Creating '雪音老師' user...")
            c.execute("INSERT INTO user (username, email, password, role, ai_personality, language, image_file) VALUES (?, ?, ?, ?, ?, ?, ?)",
                     ('雪音老師', 'yukine@internal.ai', 'ai_placeholder', 'teacher', '雪音-溫柔型', 'zh', 'default.jpg'))
        else:
            print("'雪音老師' already exists.")
    except Exception as e:
        print(f"Error creating Yukine user: {e}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    for path in ['app/app.db', 'instance/site.db']:
        fix_db(path)
    print("Database fix complete.")
