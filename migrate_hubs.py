import sqlite3

def migrate():
    conn = sqlite3.connect('jupiter_fresh.db')
    c = conn.cursor()
    
    try:
        c.execute("ALTER TABLE orders ADD COLUMN hub_id INTEGER REFERENCES hubs(id)")
        print("Migration successful: hub_id column added to orders table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
            print("Column hub_id already exists in orders table.")
        else:
            print(f"Operational error: {e}")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    migrate()
