import sqlite3
import os

db_paths = [
    'app/app.db', 
    'site.db', 
    'instance/app.db', 
    'instance/site.db'
]

for db_path in db_paths:
    if not os.path.exists(db_path):
        print(f"--- {db_path} NOT FOUND ---")
        continue
    print(f"--- Checking {db_path} ---")
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in c.fetchall()]
        print("Tables:", tables)
        if 'group_message' in tables:
            c.execute('SELECT COUNT(*) FROM group_message')
            print("Row count (group_message):", c.fetchone()[0])
            c.execute('SELECT * FROM group_message ORDER BY id DESC LIMIT 5')
            for row in c.fetchall():
                print(row)
        else:
            print("group_message NOT FOUND")
        conn.close()
    except Exception as e:
        print("Error:", e)
