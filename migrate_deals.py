import sqlite3

def migrate():
    conn = sqlite3.connect('taja_cart.db')
    c = conn.cursor()

    # 1. Insert "Deals of the Day" Main Category
    c.execute("SELECT id FROM main_categories WHERE name='Deals of the Day'")
    row = c.fetchone()
    if row:
        deals_main_id = row[0]
        print("Deals of the Day main category already exists.")
    else:
        c.execute("INSERT INTO main_categories (name, image) VALUES ('Deals of the Day', 'https://images.unsplash.com/photo-1607082348824-0a96f2a4b9da?auto=format&fit=crop&w=200&q=80')")
        deals_main_id = c.lastrowid
        print("Created Deals of the Day main category.")

    # 2. Insert "Today's Deals" Subcategory
    c.execute("SELECT id FROM categories WHERE name='Today''s Deals'")
    row = c.fetchone()
    if row:
        deals_sub_id = row[0]
        print("Today's Deals subcategory already exists.")
    else:
        c.execute("INSERT INTO categories (main_category_id, name, image) VALUES (?, ?, ?)", 
                  (deals_main_id, "Today's Deals", '/category-icons/deals.png'))
        deals_sub_id = c.lastrowid
        print("Created Today's Deals subcategory.")

    # 3. Insert the 4 Deals as Products
    deals = [
        ('Premium Dates', '1 kg', 250.0, 300.0, 4.5, '/uploads/1785948797403-a7a8ee8a.png', 1),
        ('Premium Oats', '1 kg', 200.0, 300.0, 4.5, '/uploads/1785948727422-a2fe46f9.png', 1),
        ('Dragon fruit', '1 pc', 80.0, 100.0, 4.5, '/uploads/1785948623877-ff463df5.png', 1),
        ('Avocado', '1 pc', 70.0, 100.0, 4.5, '/uploads/1785948527008-5f42e67e.png', 1)
    ]
    
    for deal in deals:
        name = deal[0]
        c.execute("SELECT id FROM products WHERE name=? AND category_id=?", (name, deals_sub_id))
        if not c.fetchone():
            c.execute(
                "INSERT INTO products (category_id, name, quantity, currentPrice, cutPrice, rating, image, in_stock) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (deals_sub_id, *deal)
            )
            print(f"Inserted deal: {name}")

    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == '__main__':
    migrate()
