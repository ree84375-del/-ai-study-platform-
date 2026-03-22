
import sqlite3
import os

# Check for database in instance or root
db_path = 'instance/site.db'
if not os.path.exists(db_path):
    db_path = 'site.db'

print(f"Using database at: {os.path.abspath(db_path)}")

if not os.path.exists(db_path):
    print("Error: Database not found.")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    print("--- Group Status ---")
    # Wrap 'group' in quotes because it's a reserved keyword in some SQL dialects
    cursor.execute('SELECT id, name, has_ai, teacher_id FROM "group" WHERE id = 1')
    group = cursor.fetchone()
    print(f"Group 1 Info: {group}")

    print("\n--- Last 5 Messages in Group 1 ---")
    cursor.execute("""
        SELECT m.id, u.username, m.content, m.created_at 
        FROM group_message m 
        JOIN user u ON m.user_id = u.id 
        WHERE m.group_id = 1 
        ORDER BY m.created_at DESC 
        LIMIT 5
    """)
    messages = cursor.fetchall()
    for msg in messages:
        print(msg)
except Exception as e:
    print(f"SQL Error: {e}")

conn.close()
