import sqlite3

conn = sqlite3.connect('app/app.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("Tables:", c.fetchall())

try:
    c.execute('SELECT id, group_id, user_id, content FROM group_message ORDER BY id DESC LIMIT 10')
    for row in c.fetchall():
        print(row)
except Exception as e:
    print("Error:", e)
conn.close()
