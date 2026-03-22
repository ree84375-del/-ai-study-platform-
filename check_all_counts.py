import sqlite3

db_path = 'instance/site.db'
print(f"--- Table row counts in {db_path} ---")
try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in c.fetchall()]
    for t in tables:
        try:
            c.execute(f"SELECT COUNT(*) FROM \"{t}\"")
            count = c.fetchone()[0]
            print(f"{t}: {count}")
        except:
            print(f"{t}: Error reading count")
    conn.close()
except Exception as e:
    print("Error:", e)
