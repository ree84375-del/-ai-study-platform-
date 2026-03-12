import os
from dotenv import load_dotenv
import psycopg2

load_dotenv('.env')
url = os.environ.get('DATABASE_URL')
conn = psycopg2.connect(url)
cur = conn.cursor()
cur.execute('SELECT email, username, role FROM "user"')
print(cur.fetchall())
cur.close()
conn.close()
