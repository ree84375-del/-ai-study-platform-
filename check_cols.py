import sqlite3

for db_path in ['app/app.db', 'instance/site.db']:
    print(f"--- Columns in {db_path} user table ---")
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("PRAGMA table_info(user)")
        cols = c.fetchall()
        for col in cols:
            print(col)
        conn.close()
    except Exception as e:
        print("Error:", e)
