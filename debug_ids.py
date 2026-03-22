
import sqlite3
import os

db_path = 'instance/site.db'
if not os.path.exists(db_path): db_path = 'site.db'

print(f"DB: {db_path}")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all groups
cursor.execute('SELECT id, name, has_ai, teacher_id FROM "group"')
groups = cursor.fetchall()
for g in groups:
    print(f"Group: {g}")

# Get all users
cursor.execute('SELECT id, username, role FROM user')
users = cursor.fetchall()
for u in users:
    print(f"User: {u}")

conn.close()
