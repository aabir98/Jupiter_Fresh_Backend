import sys
import os

filepath = "main.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

target_orders = """@app.get("/api/orders")
def get_orders(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM orders ORDER BY date DESC")
    orders = cursor.fetchall()
    for o in orders:
        o["items"] = json.loads(o["items"]) if o["items"] else []
        o["deliveryDetails"] = json.loads(o["deliveryDetails"]) if o["deliveryDetails"] else {}
    return orders"""

replacement_orders = """@app.get("/api/orders")
def get_orders(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute('''
        SELECT o.*, dp.name as dp_name, dp.phone as dp_phone 
        FROM orders o 
        LEFT JOIN delivery_personnel dp ON o.delivery_partner_id = dp.id 
        ORDER BY o.date DESC
    ''')
    orders = cursor.fetchall()
    for o in orders:
        o["items"] = json.loads(o["items"]) if o["items"] else []
        o["deliveryDetails"] = json.loads(o["deliveryDetails"]) if o["deliveryDetails"] else {}
    return orders"""

target_user_orders = """@app.get("/api/orders/user/{phone}")
def get_user_orders(phone: str, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM orders WHERE userPhone = ? ORDER BY date DESC", (phone,))
    orders = cursor.fetchall()
    for o in orders:
        o["items"] = json.loads(o["items"]) if o["items"] else []
        o["deliveryDetails"] = json.loads(o["deliveryDetails"]) if o["deliveryDetails"] else {}
    return orders"""

replacement_user_orders = """@app.get("/api/orders/user/{phone}")
def get_user_orders(phone: str, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute('''
        SELECT o.*, dp.name as dp_name, dp.phone as dp_phone 
        FROM orders o 
        LEFT JOIN delivery_personnel dp ON o.delivery_partner_id = dp.id 
        WHERE o.userPhone = ? 
        ORDER BY o.date DESC
    ''', (phone,))
    orders = cursor.fetchall()
    for o in orders:
        o["items"] = json.loads(o["items"]) if o["items"] else []
        o["deliveryDetails"] = json.loads(o["deliveryDetails"]) if o["deliveryDetails"] else {}
    return orders"""


if target_orders in content:
    content = content.replace(target_orders, replacement_orders)
    print("Successfully replaced get_orders block")
else:
    print("Could not find get_orders block")

if target_user_orders in content:
    content = content.replace(target_user_orders, replacement_user_orders)
    print("Successfully replaced get_user_orders block")
else:
    print("Could not find get_user_orders block")


with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
print("Successfully updated orders APIs")
