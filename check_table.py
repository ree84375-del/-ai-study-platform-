import sqlite3
import os

db_path = 'instance/site.db'
if not os.path.exists(db_path):
    print("Database not found site.db")
else:
    conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = [row[0] for row in cursor.fetchall()]
print("TABLES_KEYWORD:" + ",".join(tables))
conn.close()
