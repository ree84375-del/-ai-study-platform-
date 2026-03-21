import psycopg2

db_uri = "postgres://postgres:rex11255203@db.nphrkuzhedlvgfagaujq.supabase.co:5432/postgres"

try:
    print(f"Connecting to remote database...")
    conn = psycopg2.connect(db_uri)
    conn.autocommit = True
    cursor = conn.cursor()
    
    # Add column
    print("Executing ALTER TABLE command...")
    cursor.execute("ALTER TABLE chat_message ADD COLUMN IF NOT EXISTS image_data TEXT;")
    
    # Verify
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='chat_message' AND column_name='image_data';")
    if cursor.fetchone():
         print("VERIFIED: Column 'image_data' successfully added to Supabase!")
    else:
         print("FAILED: Column not found after ALTER TABLE.")
         
    cursor.close()
    conn.close()
except Exception as e:
    print(f"Error modifying Supabase: {e}")
