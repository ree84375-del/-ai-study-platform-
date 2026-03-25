import sqlite3
import os

def list_tables():
    db_paths = ['instance/app.db', 'app/app.db', 'app.db']
    db_path = None
    for p in db_paths:
        if os.path.exists(p):
            db_path = p
            break
            
    if not db_path:
        print("Database not found.")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print(f"Tables in {db_path}:")
    for t in tables:
        print(f" - {t[0]}")
    conn.close()

if __name__ == "__main__":
    list_tables()
