import json
import os
import sqlite3

# Setup SQLite database
def setup_database():
    # Create a 'data' directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    conn = sqlite3.connect('data/summaries.db')
    cursor = conn.cursor()
    
    conn.commit()
    return conn, cursor

def get_recent_summaries(cursor, limit=5):
    cursor.execute('''
        SELECT url, summary, tags, created_at 
        FROM summaries 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (limit,))
    return cursor.fetchall()

conn, cursor = setup_database()

recent = get_recent_summaries(cursor)
for url, summary, tags, date in recent:
    print(f"\nURL: {url}")
    print(f"Summary: {summary}")
    print(f"Tags: {json.loads(tags)}")
    print(f"Date: {date}\n")

# At the very end of the file
conn.close()