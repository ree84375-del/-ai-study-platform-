import sqlite3
import datetime

db_path = 'app/app.db'
print(f"--- Initializing {db_path} via raw SQLite ---")

conn = sqlite3.connect(db_path)
c = conn.cursor()

# 1. Create group_message table if it doesn't exist
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
    print(f"Error creating table: {e}")

# 2. Check for Yukine user
c.execute("SELECT id FROM user WHERE username = '雪音老師'")
yukine = c.fetchone()

if not yukine:
    print("Inserting '雪音老師' user...")
    # Use a dummy hashed password (compatible with bcrypt $2b$12$...)
    dummy_hash = '$2b$12$KyIDB3r.qV6bF6.80vOaO.mZ7eU6.R/C5F.0/YvYvYvYvYvYvYvY' 
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('''
        INSERT INTO user (username, email, image_file, password, role, ai_personality, language, last_active_at)
        VALUES ('雪音老師', 'yukine@antigravity.ai', 'default.jpg', ?, 'teacher', '雪音-溫柔型', 'zh', ?)
    ''', (dummy_hash, now))
    conn.commit()
    print("Inserted '雪音老師'.")
else:
    print(f"User '雪音老師' already exists (ID: {yukine[0]})")

# 3. Ensure AI enabled for all groups
c.execute("UPDATE \"group\" SET has_ai = 1")
conn.commit()
print("Updated all groups to have has_ai=1.")

conn.close()
print("Raw initialization complete.")
