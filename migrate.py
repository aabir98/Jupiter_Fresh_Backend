import sqlite3

def migrate():
    conn = sqlite3.connect('taja_cart.db')
    c = conn.cursor()
    
    # Create main_categories table
    c.execute('''CREATE TABLE IF NOT EXISTS main_categories (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT UNIQUE NOT NULL,
      image TEXT
    )''')
    
    # Insert main categories if empty
    c.execute('SELECT COUNT(*) FROM main_categories')
    if c.fetchone()[0] == 0:
        main_cats = [
            ('Fresh', 'https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&w=200&q=80'),
            ('Food', 'https://images.unsplash.com/photo-1504674900247-0877df9cc836?auto=format&fit=crop&w=200&q=80'),
            ('Fashion', 'https://images.unsplash.com/photo-1445205170230-053b83016050?auto=format&fit=crop&w=200&q=80'),
            ('Electronics', 'https://images.unsplash.com/photo-1498049794561-7780e7231661?auto=format&fit=crop&w=200&q=80')
        ]
        c.executemany('INSERT INTO main_categories (name, image) VALUES (?, ?)', main_cats)
        conn.commit()

    # Get 'Fresh' ID
    c.execute("SELECT id FROM main_categories WHERE name='Fresh'")
    fresh_row = c.fetchone()
    if fresh_row:
        fresh_id = fresh_row[0]
        
        # Add column to categories
        try:
            c.execute('ALTER TABLE categories ADD COLUMN main_category_id INTEGER REFERENCES main_categories(id) ON DELETE CASCADE')
        except sqlite3.OperationalError:
            pass
            
        # Update existing categories
        c.execute('UPDATE categories SET main_category_id = ? WHERE main_category_id IS NULL', (fresh_id,))
        conn.commit()
        
    conn.close()
    print('Migration successful.')

if __name__ == '__main__':
    migrate()
