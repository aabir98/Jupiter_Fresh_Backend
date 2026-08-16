import sys

filepath = "main.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

helper_code = """
def get_dp_with_true_rating(cursor, dp_id):
    cursor.execute("SELECT * FROM delivery_personnel WHERE id = ?", (dp_id,))
    dp_row = cursor.fetchone()
    if not dp_row:
        return None
    
    dp = dict(dp_row)
    
    cursor.execute("SELECT delivery_partner_rating FROM orders WHERE delivery_partner_id = ? AND status = 'Delivered'", (dp_id,))
    orders = cursor.fetchall()
    
    if not orders:
        dp['rating'] = 0.0
        dp['total_ratings'] = 0
    else:
        total = 0
        for o in orders:
            if o['delivery_partner_rating'] is not None:
                total += o['delivery_partner_rating']
            else:
                total += 2.5
        dp['rating'] = total / len(orders)
        dp['total_ratings'] = len(orders)
        
    return dp
"""

if "app = FastAPI()" in content and "def get_dp_with_true_rating" not in content:
    content = content.replace("app = FastAPI()", helper_code + "\napp = FastAPI()")

# Replace delivery_login
login_block = """    if existing:
        if phone:
            cursor.execute("UPDATE delivery_personnel SET phone = ?, name = ?, picture = ? WHERE email = ?", (phone, name, picture, email))
            db.commit()
            cursor.execute("SELECT * FROM delivery_personnel WHERE email = ?", (email,))
            existing = cursor.fetchone()
        return dict(existing)
    else:
        if not phone or not hub_id:
            raise HTTPException(status_code=400, detail="Phone and Hub ID are required for first time login")
        cursor.execute('''INSERT INTO delivery_personnel (email, name, phone, picture, hub_id) VALUES (?, ?, ?, ?, ?)''',
                       (email, name, phone, picture, hub_id))
        db.commit()
        new_id = cursor.lastrowid
        cursor.execute("SELECT * FROM delivery_personnel WHERE id = ?", (new_id,))
        return dict(cursor.fetchone())"""

login_replacement = """    if existing:
        if phone:
            cursor.execute("UPDATE delivery_personnel SET phone = ?, name = ?, picture = ? WHERE email = ?", (phone, name, picture, email))
            db.commit()
            cursor.execute("SELECT * FROM delivery_personnel WHERE email = ?", (email,))
            existing = cursor.fetchone()
        return get_dp_with_true_rating(cursor, existing['id'])
    else:
        if not phone or not hub_id:
            raise HTTPException(status_code=400, detail="Phone and Hub ID are required for first time login")
        cursor.execute('''INSERT INTO delivery_personnel (email, name, phone, picture, hub_id) VALUES (?, ?, ?, ?, ?)''',
                       (email, name, phone, picture, hub_id))
        db.commit()
        new_id = cursor.lastrowid
        return get_dp_with_true_rating(cursor, new_id)"""

content = content.replace(login_block, login_replacement)

# Replace get_delivery_personnel
get_block = """@app.get("/api/delivery-personnel/{dp_id}")
def get_delivery_personnel(dp_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT id, name, phone, picture, rating FROM delivery_personnel WHERE id = ?", (dp_id,))
    dp = cursor.fetchone()
    if not dp:
        raise HTTPException(status_code=404, detail="Delivery personnel not found")
    return dict(dp)"""

get_replacement = """@app.get("/api/delivery-personnel/{dp_id}")
def get_delivery_personnel(dp_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    dp = get_dp_with_true_rating(cursor, dp_id)
    if not dp:
        raise HTTPException(status_code=404, detail="Delivery personnel not found")
    return dp"""

content = content.replace(get_block, get_replacement)

# Replace update_delivery_personnel
put_block = """    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Delivery personnel not found")
        
    cursor.execute("SELECT * FROM delivery_personnel WHERE id = ?", (dp_id,))
    return dict(cursor.fetchone())"""

put_replacement = """    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Delivery personnel not found")
        
    return get_dp_with_true_rating(cursor, dp_id)"""

content = content.replace(put_block, put_replacement)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
print("Successfully patched rating logic in main.py")
