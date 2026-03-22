import sqlite3

conn = sqlite3.connect('app/app.db')
c = conn.cursor()
c.execute('SELECT id, group_id, user_id, content FROM group_message ORDER BY id DESC LIMIT 10')
for row in c.fetchall():
    print(row)
conn.close()
