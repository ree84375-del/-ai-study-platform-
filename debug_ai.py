
import sqlite3
import os

db_path = 'instance/site.db'
if not os.path.exists(db_path): db_path = 'site.db'

print(f"DB: {db_path}")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute('SELECT id, name, has_ai FROM "group" WHERE id=1')
print(f"Group 1: {cursor.fetchone()}")

cursor.execute('SELECT id, username FROM user WHERE username IN ("雪音老師", "雪音")')
print(f"Users: {cursor.fetchall()}")

cursor.execute('SELECT m.id, u.username, m.content FROM group_message m JOIN user u ON m.user_id = u.id WHERE m.group_id=1 ORDER BY m.id DESC LIMIT 5')
msgs = cursor.fetchall()
for m in msgs: print(f"MSG: {m}")
conn.close()
