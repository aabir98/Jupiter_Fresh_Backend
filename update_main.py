import sys
import os

filepath = "main.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Replace the INSERT INTO orders block
target_insert = """    cursor.execute(
        "INSERT INTO orders (id, date, items, grandTotal, deliveryDetails, userEmail, userPhone, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (order_id, date, json.dumps(items), grandTotal, json.dumps(deliveryDetails), userEmail, userPhone, status)
    )"""

replacement_insert = """    import math

    def haversine(lat1, lon1, lat2, lon2):
        if lat1 is None or lon1 is None or lat2 is None or lon2 is None: return 999999
        R = 6371
        dLat = math.radians(lat2 - lat1)
        dLon = math.radians(lon2 - lon1)
        a = math.sin(dLat/2) * math.sin(dLat/2) + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dLon/2) * math.sin(dLon/2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    assigned_delivery_id = None
    user_lat = deliveryDetails.get("lat")
    user_lng = deliveryDetails.get("lng")

    if user_lat is not None and user_lng is not None:
        cursor.execute("SELECT * FROM hubs WHERE is_active = 1")
        active_hubs = cursor.fetchall()
        valid_hubs = []
        for h in active_hubs:
            dist = haversine(user_lat, user_lng, h["lat"], h["lng"])
            if dist <= h["radius_km"]:
                valid_hubs.append(h["id"])
        
        if valid_hubs:
            hub_ids_str = ",".join(map(str, valid_hubs))
            # Find delivery personnel in valid hubs, ordered by number of active orders
            query = f'''
                SELECT dp.id, COUNT(o.id) as active_orders 
                FROM delivery_personnel dp
                LEFT JOIN orders o ON dp.id = o.delivery_partner_id AND o.status NOT IN ('Delivered', 'Cancelled')
                WHERE dp.hub_id IN ({hub_ids_str}) AND dp.is_active = 1
                GROUP BY dp.id
                ORDER BY active_orders ASC, dp.id ASC
                LIMIT 1
            '''
            cursor.execute(query)
            dp_row = cursor.fetchone()
            if dp_row:
                assigned_delivery_id = dp_row["id"]
    
    if not assigned_delivery_id:
        # Fallback to any active delivery personnel
        query = '''
            SELECT dp.id, COUNT(o.id) as active_orders 
            FROM delivery_personnel dp
            LEFT JOIN orders o ON dp.id = o.delivery_partner_id AND o.status NOT IN ('Delivered', 'Cancelled')
            WHERE dp.is_active = 1
            GROUP BY dp.id
            ORDER BY active_orders ASC, dp.id ASC
            LIMIT 1
        '''
        cursor.execute(query)
        dp_row = cursor.fetchone()
        if dp_row:
            assigned_delivery_id = dp_row["id"]

    cursor.execute(
        "INSERT INTO orders (id, date, items, grandTotal, deliveryDetails, userEmail, userPhone, status, delivery_partner_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (order_id, date, json.dumps(items), grandTotal, json.dumps(deliveryDetails), userEmail, userPhone, status, assigned_delivery_id)
    )"""

if target_insert in content:
    content = content.replace(target_insert, replacement_insert)
    print("Successfully replaced INSERT INTO orders block")
else:
    print("Could not find INSERT INTO orders block")
    sys.exit(1)


# 2. Append the new Delivery APIs
delivery_apis = """

# --- DELIVERY API ---

@app.post("/api/delivery/login")
async def delivery_login(request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    email = data.get("email")
    name = data.get("name")
    phone = data.get("phone")
    picture = data.get("picture")
    hub_id = data.get("hub_id")

    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    cursor = db.cursor()
    cursor.execute("SELECT * FROM delivery_personnel WHERE email = ?", (email,))
    existing = cursor.fetchone()

    if existing:
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
        return dict(cursor.fetchone())

@app.get("/api/delivery/orders/{email}")
def get_delivery_orders(email: str, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT id FROM delivery_personnel WHERE email = ?", (email,))
    dp = cursor.fetchone()
    if not dp:
        raise HTTPException(status_code=404, detail="Delivery personnel not found")
    
    cursor.execute("SELECT * FROM orders WHERE delivery_partner_id = ? ORDER BY date DESC", (dp["id"],))
    orders = cursor.fetchall()
    for o in orders:
        o["items"] = json.loads(o["items"]) if o["items"] else []
        o["deliveryDetails"] = json.loads(o["deliveryDetails"]) if o["deliveryDetails"] else {}
    return orders

@app.patch("/api/orders/{order_id}/rate-delivery")
async def rate_delivery(order_id: str, request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    rating = data.get("rating")
    
    if not rating:
        raise HTTPException(status_code=400, detail="Rating is required")
        
    cursor = db.cursor()
    cursor.execute("UPDATE orders SET delivery_partner_rating = ? WHERE id = ?", (rating, order_id))
    
    cursor.execute("SELECT delivery_partner_id FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if order and order["delivery_partner_id"]:
        dp_id = order["delivery_partner_id"]
        cursor.execute("SELECT rating, total_ratings FROM delivery_personnel WHERE id = ?", (dp_id,))
        dp = cursor.fetchone()
        if dp:
            new_total = dp["total_ratings"] + 1
            new_rating = ((dp["rating"] * dp["total_ratings"]) + rating) / new_total
            cursor.execute("UPDATE delivery_personnel SET rating = ?, total_ratings = ? WHERE id = ?", (new_rating, new_total, dp_id))
            
    db.commit()
    return {"message": "Delivery rated successfully"}

@app.get("/api/delivery-personnel/{dp_id}")
def get_delivery_personnel(dp_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT id, name, phone, picture, rating FROM delivery_personnel WHERE id = ?", (dp_id,))
    dp = cursor.fetchone()
    if not dp:
        raise HTTPException(status_code=404, detail="Delivery personnel not found")
    return dict(dp)
"""

content += delivery_apis

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
print("Successfully appended Delivery APIs")
