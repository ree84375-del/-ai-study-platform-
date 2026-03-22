import sqlite3

db_path = 'app/app.db'
print(f"--- Checking {db_path} ---")
try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT id, username FROM user WHERE username = '雪音老師'")
    user = c.fetchone()
    if user:
        print(f"Found: {user}")
    else:
        print("User '雪音老師' NOT FOUND")
        c.execute("SELECT id, username FROM user LIMIT 10")
        print("Available users:", c.fetchall())
    conn.close()
except Exception as e:
    print("Error:", e)
