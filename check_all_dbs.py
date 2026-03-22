import sqlite3

for db_path in ['app/app.db', 'site.db']:
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
        else:
            print("group_message NOT FOUND")
        conn.close()
    except Exception as e:
        print("Error:", e)
