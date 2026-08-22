import sqlite3

def migrate():
    conn = sqlite3.connect('jupiter_fresh.db')
    c = conn.cursor()
    
    # User Notifications Table
    c.execute('''CREATE TABLE IF NOT EXISTS user_notifications (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      userEmail TEXT NOT NULL,
      text TEXT NOT NULL,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (userEmail) REFERENCES customers (email) ON DELETE CASCADE
    )''')
    
    conn.commit()
    conn.close()
    print("Migration successful: user_notifications table verified/created.")

if __name__ == "__main__":
    migrate()
