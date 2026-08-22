import os
import json
import time
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Depends, Request, Response, HTTPException, UploadFile, Form, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from database import get_db, init_db
import sqlite3
import shutil
import firebase_admin
from firebase_admin import credentials, messaging


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

app = FastAPI()

# Initialize Firebase Admin SDK
try:
    # This will use the GOOGLE_APPLICATION_CREDENTIALS environment variable
    # Or default service account if running on GCP. 
    # Otherwise, you need to provide credentials.Certificate("path/to/serviceAccountKey.json")
    if not firebase_admin._apps:
        firebase_admin.initialize_app()
    print("Firebase Admin SDK initialized successfully.")
except Exception as e:
    print(f"Failed to initialize Firebase Admin SDK. Push notifications will not work. Error: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.on_event("startup")
def on_startup():
    init_db()
    
    # Initialize VAPID keys if not present
    for conn in get_db():
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='VAPID_PRIVATE_KEY'")
        if not c.fetchone():
            try:
                vapid_private_key = "pNgFKjIiXbcgsk10lArL6P_s4djzrZCuJtM8fxUt1vA"
                vapid_public_key = "BNPAHBlQULCX22LDEDAVz0Xp19-jWG0WCdAlxFtM6jyxoPh77U1yBEf9fOWAYhX2cKAp2v-oH5z3B9ObVUu5G9k"
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('VAPID_PRIVATE_KEY', ?)", (vapid_private_key,))
                c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('VAPID_PUBLIC_KEY', ?)", (vapid_public_key,))
                conn.commit()
                print("Generated and saved new VAPID keys.")
            except Exception as e:
                print(f"Error saving VAPID keys: {e}")
        break

# --- ADMIN IN-APP NOTIFICATIONS API ---

@app.get("/api/admin/alerts")
def get_admin_alerts(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM admin_alerts ORDER BY created_at DESC")
    alerts = [dict(row) for row in cursor.fetchall()]
    return alerts

@app.patch("/api/admin/alerts/{alert_id}/read")
def mark_admin_alert_read(alert_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("UPDATE admin_alerts SET is_read = 1 WHERE id = ?", (alert_id,))
    db.commit()
    return {"message": "Alert marked as read"}

@app.patch("/api/admin/alerts/read_all")
def mark_all_admin_alerts_read(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("UPDATE admin_alerts SET is_read = 1 WHERE is_read = 0")
    db.commit()
    return {"message": "All alerts marked as read"}

# --- ADMIN PUSH NOTIFICATIONS API ---

@app.get("/api/admin/vapid_public_key")
def get_vapid_public_key(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT value FROM settings WHERE key='VAPID_PUBLIC_KEY'")
    row = cursor.fetchone()
    if row:
        return {"public_key": row["value"]}
    raise HTTPException(status_code=404, detail="VAPID keys not generated yet")

@app.post("/api/admin/subscribe")
async def admin_subscribe(request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    endpoint = data.get("endpoint")
    keys = data.get("keys", {})
    p256dh = keys.get("p256dh")
    auth = keys.get("auth")

    if not endpoint or not p256dh or not auth:
        raise HTTPException(status_code=400, detail="Missing subscription info")

    cursor = db.cursor()
    cursor.execute('''
        INSERT INTO admin_subscriptions (endpoint, p256dh, auth) 
        VALUES (?, ?, ?)
        ON CONFLICT(endpoint) DO UPDATE SET p256dh=excluded.p256dh, auth=excluded.auth
    ''', (endpoint, p256dh, auth))
    db.commit()
    return {"message": "Subscription saved"}

def save_upload_file(upload_file: UploadFile) -> str:
    timestamp = int(time.time() * 1000)
    # Simple unique suffix
    unique_suffix = f"{timestamp}-{os.urandom(4).hex()}"
    _, ext = os.path.splitext(upload_file.filename)
    filename = f"{unique_suffix}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    return f"/uploads/{filename}"

# --- ORDERS API ---

@app.post("/api/orders")
async def create_order(request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    order_id = data.get("id")
    date = data.get("date")
    items = data.get("items", [])
    grandTotal = data.get("grandTotal")
    deliveryDetails = data.get("deliveryDetails", {})
    userEmail = deliveryDetails.get("email", "")
    userPhone = deliveryDetails.get("phone", "")
    status = "Placed"

    cursor = db.cursor()
    import math

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
        nearest_hub_id = None
        min_dist = float('inf')
        for h in active_hubs:
            dist = haversine(user_lat, user_lng, h["lat"], h["lng"])
            if dist <= h["radius_km"] and dist < min_dist:
                min_dist = dist
                nearest_hub_id = h["id"]
        
        if nearest_hub_id is not None:
            # Find an available delivery personnel (0 active orders) with lowest completed orders, then highest rating
            query = f'''
                WITH dp_stats AS (
                    SELECT dp.id,
                           (SELECT COUNT(*) FROM orders o1 WHERE o1.delivery_partner_id = dp.id AND o1.status NOT IN ('Delivered', 'Cancelled')) as active_orders,
                           (SELECT COUNT(*) FROM orders o2 WHERE o2.delivery_partner_id = dp.id AND o2.status = 'Delivered') as completed_deliveries,
                           COALESCE(
                               (SELECT SUM(COALESCE(o3.delivery_partner_rating, 2.5)) * 1.0 / NULLIF(COUNT(o3.id), 0)
                                FROM orders o3 WHERE o3.delivery_partner_id = dp.id AND o3.status = 'Delivered'),
                               0.0
                           ) as actual_rating
                    FROM delivery_personnel dp
                    WHERE dp.hub_id = {nearest_hub_id} AND dp.is_active = 1 AND dp.is_disabled = 0 AND dp.is_deleted = 0
                )
                SELECT id
                FROM dp_stats
                WHERE active_orders = 0
                ORDER BY completed_deliveries ASC, actual_rating DESC, id ASC
                LIMIT 1
            '''
            cursor.execute(query)
            dp_row = cursor.fetchone()
            if dp_row:
                assigned_delivery_id = dp_row["id"]

    import random
    delivery_pin = f"{random.randint(1000, 9999)}"

    cursor.execute(
        "INSERT INTO orders (id, date, items, grandTotal, deliveryDetails, userEmail, userPhone, status, delivery_partner_id, delivery_pin, hub_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (order_id, date, json.dumps(items), grandTotal, json.dumps(deliveryDetails), userEmail, userPhone, status, assigned_delivery_id, delivery_pin, nearest_hub_id)
    )
    
    # Save the order notification to the admin alerts database
    customer_name = deliveryDetails.get("name", "A customer")
    customer_addr = deliveryDetails.get("building", "").strip()
    if not customer_addr:
        customer_addr = "an unknown address"
        
    alert_text = f"{customer_name} from {customer_addr} has placed an order of ₹{grandTotal}"
    cursor.execute("INSERT INTO admin_alerts (text) VALUES (?)", (alert_text,))
    
    # Save the user-specific order notification
    if userEmail:
        item_count = sum(item.get("qty", 1) for item in items)
        user_notif_text = f"Your order of order id {order_id} with {item_count} items of total price ₹{grandTotal} is placed"
        cursor.execute("INSERT INTO user_notifications (userEmail, text) VALUES (?, ?)", (userEmail, user_notif_text))
        
    db.commit()

    # Trigger Push Notification to Delivery Partner (if auto-assigned)
    if assigned_delivery_id:
        try:
            import firebase_admin
            from firebase_admin import messaging
            cursor.execute("SELECT email FROM delivery_personnel WHERE id=?", (assigned_delivery_id,))
            dp_row = cursor.fetchone()
            if dp_row:
                dp_email = dp_row['email']
                cursor.execute("SELECT token FROM device_tokens WHERE identifier=? AND role='delivery'", (dp_email,))
                dp_tokens = [r['token'] for r in cursor.fetchall()]
                if dp_tokens and firebase_admin._apps:
                    fcm_msg = messaging.MulticastMessage(
                        notification=messaging.Notification(
                            title="New Delivery Assigned! 📦",
                            body="You have been assigned a new order. Please open the app to check."
                        ),
                        tokens=dp_tokens,
                    )
                    messaging.send_each_for_multicast(fcm_msg)
        except Exception as e:
            print(f"Failed to send FCM push to delivery partner: {e}")

    # Trigger Push Notification to Admins
    try:
        # 1. FCM Push Notifications (For Admin Mobile App)
        try:
            import firebase_admin
            from firebase_admin import messaging
            cursor.execute("SELECT token FROM device_tokens WHERE role='admin'")
            admin_tokens = [row['token'] for row in cursor.fetchall()]
            if admin_tokens and firebase_admin._apps:
                fcm_message = messaging.MulticastMessage(
                    notification=messaging.Notification(
                        title="New Order Placed! 🛍️",
                        body=f"{customer_name} from {customer_addr} has placed an order of ₹{grandTotal}"
                    ),
                    tokens=admin_tokens,
                )
                response = messaging.send_each_for_multicast(fcm_message)
                print(f"Successfully sent {response.success_count} FCM messages to admin app")
        except Exception as e:
            print(f"Failed to send FCM push notification to admin app: {e}")

        # 2. Web Push Notifications (For Admin Web Dashboard)
        cursor.execute("SELECT value FROM settings WHERE key='VAPID_PRIVATE_KEY'")
        priv_key_row = cursor.fetchone()
        if priv_key_row:
            vapid_private_key = priv_key_row["value"]
            cursor.execute("SELECT * FROM admin_subscriptions")
            subs = cursor.fetchall()
            if subs:
                from pywebpush import webpush, WebPushException
                
                payload = json.dumps({
                    "title": "New Order Placed! 🛍️",
                    "body": f"{customer_name} from {customer_addr} has placed an order of ₹{grandTotal}",
                    "url": "/admin/orders?status=Placed"
                })
                
                for sub in subs:
                    try:
                        webpush(
                            subscription_info={
                                "endpoint": sub["endpoint"],
                                "keys": {
                                    "p256dh": sub["p256dh"],
                                    "auth": sub["auth"]
                                }
                            },
                            data=payload,
                            vapid_private_key=vapid_private_key,
                            vapid_claims={"sub": "mailto:admin@tajacart.in"}
                        )
                    except WebPushException as ex:
                        if ex.response and ex.response.status_code in (404, 410):
                            cursor.execute("DELETE FROM admin_subscriptions WHERE id=?", (sub["id"],))
                            db.commit()
                        print(f"WebPush Error: {ex}")
    except Exception as e:
        print(f"Failed to send push notifications: {e}")

    return {"message": "Order created successfully", "id": order_id, "delivery_pin": delivery_pin}

@app.get("/api/orders")
def get_orders(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute('''
        SELECT o.*, dp.name as dp_name, dp.phone as dp_phone, h.name as hub_name
        FROM orders o 
        LEFT JOIN delivery_personnel dp ON o.delivery_partner_id = dp.id 
        LEFT JOIN hubs h ON o.hub_id = h.id
        ORDER BY o.date DESC
    ''')
    orders = cursor.fetchall()
    for o in orders:
        o["items"] = json.loads(o["items"]) if o["items"] else []
        o["deliveryDetails"] = json.loads(o["deliveryDetails"]) if o["deliveryDetails"] else {}
    return orders

@app.get("/api/orders/user/{phone}")
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
    return orders

@app.patch("/api/orders/{order_id}/status")
async def update_order_status(order_id: str, request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    status = data.get("status")
    eta = data.get("eta")
    pin = data.get("pin") or data.get("delivery_pin")

    cursor = db.cursor()
    
    cursor.execute('''
        SELECT o.userEmail, o.delivery_pin, dp.name as dp_name, o.hub_id, o.delivery_partner_id
        FROM orders o 
        LEFT JOIN delivery_personnel dp ON o.delivery_partner_id = dp.id 
        WHERE o.id = ?
    ''', (order_id,))
    order_row = cursor.fetchone()
    if not order_row:
        raise HTTPException(status_code=404, detail="Order not found")

    userEmail = order_row["userEmail"]
    stored_pin = order_row.get("delivery_pin")
    dp_name = order_row.get("dp_name")
    hub_id = order_row.get("hub_id")
    dp_id = order_row.get("delivery_partner_id")

    if status == "Delivered":
        if stored_pin and (not pin or str(pin).strip() != str(stored_pin).strip()):
            raise HTTPException(status_code=400, detail="Wrong Delivery Pin. Ask Delivery Pin from customer")

    import datetime
    if status == "On the way":
        picked_up_at = datetime.datetime.now().isoformat()
        if eta is not None:
            cursor.execute("UPDATE orders SET status = ?, eta = ?, picked_up_at = ? WHERE id = ?", (status, eta, picked_up_at, order_id))
        else:
            cursor.execute("UPDATE orders SET status = ?, picked_up_at = ? WHERE id = ?", (status, picked_up_at, order_id))
    else:
        if eta is not None:
            cursor.execute("UPDATE orders SET status = ?, eta = ? WHERE id = ?", (status, eta, order_id))
        else:
            cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        
    if userEmail and status in ["Picked Up", "Delivered", "Arrived"]:
        if status == "Arrived":
            notif_text = f"Delivery man {dp_name or ''} with order {order_id} have arrived"
        else:
            notif_text = f"Your order {order_id} is {status.lower()}"
        cursor.execute("INSERT INTO user_notifications (userEmail, text) VALUES (?, ?)", (userEmail, notif_text))
        
    db.commit()
    
    # Auto-assign queued orders
    if status in ["Delivered", "Cancelled"] and dp_id and hub_id:
        cursor.execute("SELECT COUNT(*) as active FROM orders WHERE delivery_partner_id = ? AND status NOT IN ('Delivered', 'Cancelled')", (dp_id,))
        if cursor.fetchone()["active"] == 0:
            cursor.execute("SELECT id FROM orders WHERE hub_id = ? AND delivery_partner_id IS NULL AND status NOT IN ('Delivered', 'Cancelled') ORDER BY date ASC LIMIT 1", (hub_id,))
            next_order = cursor.fetchone()
            if next_order:
                cursor.execute("UPDATE orders SET delivery_partner_id = ? WHERE id = ?", (dp_id, next_order["id"]))
                db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return {"message": "Order status updated successfully", "id": order_id, "status": status, "eta": eta}

@app.delete("/api/orders/{order_id}")
def delete_order(order_id: str, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"message": "Order deleted successfully", "id": order_id}

@app.patch("/api/orders/{order_id}/rate")
async def rate_order(order_id: str, request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    rating = data.get("rating")
    review = data.get("review")

    cursor = db.cursor()
    cursor.execute("UPDATE orders SET rating = ?, review = ? WHERE id = ?", (rating, review, order_id))
    if cursor.rowcount == 0:
        db.commit()
        raise HTTPException(status_code=404, detail="Order not found")
    
    cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if order:
        try:
            details = json.loads(order["deliveryDetails"]) if order["deliveryDetails"] else {}
            customer_name = details.get("name", "Anonymous")
            cursor.execute('''INSERT INTO reviews (customer_name, rating, text, is_featured, order_id) VALUES (?, ?, ?, 0, ?)
                              ON CONFLICT(order_id) DO UPDATE SET rating = excluded.rating, text = excluded.text''',
                           (customer_name, rating, review, order_id))
        except Exception:
            pass
    db.commit()
    return {"message": "Order rated successfully", "id": order_id, "rating": rating, "review": review}

# --- ADDRESSES API ---

@app.get("/api/addresses/{email}")
def get_addresses(email: str, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM saved_addresses WHERE userEmail = ? ORDER BY id DESC", (email,))
    return cursor.fetchall()

@app.post("/api/addresses")
async def save_address(request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    userEmail = data.get("userEmail")
    label = data.get("label")
    address = data.get("address")
    landmark = data.get("landmark")
    lat = data.get("lat")
    lng = data.get("lng")

    if not userEmail or not label or not address or lat is None or lng is None:
        raise HTTPException(status_code=400, detail="Missing required fields")

    cursor = db.cursor()
    cursor.execute("INSERT INTO saved_addresses (userEmail, label, address, landmark, lat, lng) VALUES (?, ?, ?, ?, ?, ?)",
                   (userEmail, label, address, landmark, lat, lng))
    db.commit()
    return Response(content=json.dumps({"message": "Address saved successfully", "id": cursor.lastrowid}), status_code=201, media_type="application/json")

@app.put("/api/addresses/{address_id}")
async def update_address(address_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    label = data.get("label")
    address = data.get("address")
    landmark = data.get("landmark")
    lat = data.get("lat")
    lng = data.get("lng")

    if not label or not address or lat is None or lng is None:
        raise HTTPException(status_code=400, detail="Missing required fields")

    cursor = db.cursor()
    cursor.execute("UPDATE saved_addresses SET label = ?, address = ?, landmark = ?, lat = ?, lng = ? WHERE id = ?",
                   (label, address, landmark, lat, lng, address_id))
    db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Address not found")
    return {"message": "Address updated successfully"}

@app.delete("/api/addresses/{address_id}")
def delete_address(address_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM saved_addresses WHERE id = ?", (address_id,))
    db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Address not found")
    return {"message": "Address deleted successfully"}

# --- CUSTOMERS API ---

@app.post("/api/customers")
async def save_customer(request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    email = data.get("email")
    name = data.get("name")
    phone = data.get("phone")
    picture = data.get("picture")
    joinedDate = time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())

    cursor = db.cursor()
    cursor.execute('''INSERT INTO customers (email, name, phone, picture, joinedDate) VALUES (?, ?, ?, ?, ?)
                      ON CONFLICT(email) DO UPDATE SET phone=excluded.phone, name=excluded.name, picture=excluded.picture''',
                   (email, name, phone, picture, joinedDate))
    db.commit()
    return {"message": "Customer saved successfully", "email": email}

@app.get("/api/customers/{email}")
def get_customer(email: str, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM customers WHERE email = ?", (email,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")
    return row

@app.get("/api/customers")
def get_customers(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute('''SELECT c.*, COUNT(o.id) as orderCount 
                      FROM customers c LEFT JOIN orders o ON c.email = o.userEmail 
                      GROUP BY c.email ORDER BY c.joinedDate DESC''')
    return cursor.fetchall()

# --- OFFERS API ---

@app.get("/api/offers")
def get_offers(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM offers ORDER BY valid_until DESC")
    return cursor.fetchall()

@app.post("/api/offers")
async def create_offer(request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    code = data.get("code")
    event_name = data.get("event_name")
    discount_percent = data.get("discount_percent")
    valid_until = data.get("valid_until")

    if not code or not event_name or discount_percent is None or not valid_until:
        raise HTTPException(status_code=400, detail="Missing required fields")

    cursor = db.cursor()
    cursor.execute("INSERT INTO offers (code, event_name, discount_percent, valid_until) VALUES (?, ?, ?, ?)",
                   (code, event_name, discount_percent, valid_until))
    db.commit()
    return Response(content=json.dumps({"message": "Offer created", "id": cursor.lastrowid}), status_code=201, media_type="application/json")

@app.put("/api/offers/{offer_id}")
async def update_offer(offer_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    cursor = db.cursor()
    cursor.execute("UPDATE offers SET code = ?, event_name = ?, discount_percent = ?, valid_until = ? WHERE id = ?",
                   (data.get("code"), data.get("event_name"), data.get("discount_percent"), data.get("valid_until"), offer_id))
    db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Offer not found")
    return {"message": "Offer updated successfully"}

@app.delete("/api/offers/{offer_id}")
def delete_offer(offer_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM offers WHERE id = ?", (offer_id,))
    db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Offer not found")
    return {"message": "Offer deleted successfully"}

# --- SETTINGS API ---

@app.get("/api/settings")
def get_settings(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM settings")
    return cursor.fetchall()

@app.post("/api/settings")
async def update_settings(request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    cursor = db.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (data.get("key"), data.get("value")))
    db.commit()
    return {"message": "Setting updated successfully"}

# --- HUBS API ---

@app.get("/api/hubs")
def get_hubs(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM hubs ORDER BY id DESC")
    return cursor.fetchall()

@app.post("/api/hubs")
async def create_hub(request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    name = data.get("name")
    lat = data.get("lat")
    lng = data.get("lng")
    radius_km = data.get("radius_km")
    is_active = data.get("is_active", True)

    if not name or lat is None or lng is None or radius_km is None:
        raise HTTPException(status_code=400, detail="Missing required fields")

    cursor = db.cursor()
    cursor.execute("INSERT INTO hubs (name, lat, lng, radius_km, is_active) VALUES (?, ?, ?, ?, ?)",
                   (name, lat, lng, radius_km, 1 if is_active else 0))
    db.commit()
    return Response(content=json.dumps({"message": "Hub created", "id": cursor.lastrowid}), status_code=201, media_type="application/json")

@app.put("/api/hubs/{hub_id}")
async def update_hub(hub_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    cursor = db.cursor()
    cursor.execute("UPDATE hubs SET name = ?, lat = ?, lng = ?, radius_km = ?, is_active = ? WHERE id = ?",
                   (data.get("name"), data.get("lat"), data.get("lng"), data.get("radius_km"), 1 if data.get("is_active") else 0, hub_id))
    db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Hub not found")
    return {"message": "Hub updated successfully"}

@app.delete("/api/hubs/{hub_id}")
def delete_hub(hub_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM hubs WHERE id = ?", (hub_id,))
    db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Hub not found")
    return {"message": "Hub deleted successfully"}

# --- ANNOUNCEMENTS API ---

@app.get("/api/announcements")
def get_announcements(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM announcements")
    return cursor.fetchall()

@app.post("/api/announcements")
async def create_announcement(request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    if not data.get("text"):
        raise HTTPException(status_code=400, detail="Missing announcement text")

    cursor = db.cursor()
    cursor.execute("INSERT INTO announcements (text) VALUES (?)", (data.get("text"),))
    db.commit()
    return Response(content=json.dumps({"message": "Announcement created", "id": cursor.lastrowid}), status_code=201, media_type="application/json")

@app.put("/api/announcements/{ann_id}")
async def update_announcement(ann_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    if not data.get("text"):
        raise HTTPException(status_code=400, detail="Missing announcement text")
    
    cursor = db.cursor()
    cursor.execute("UPDATE announcements SET text = ? WHERE id = ?", (data.get("text"), ann_id))
    db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return {"message": "Announcement updated successfully"}

@app.delete("/api/announcements/{ann_id}")
def delete_announcement(ann_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM announcements WHERE id = ?", (ann_id,))
    db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return {"message": "Announcement deleted successfully"}

# --- REVIEWS API ---

@app.get("/api/reviews")
def get_reviews(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM reviews ORDER BY id DESC")
    return cursor.fetchall()

@app.get("/api/reviews/featured")
def get_featured_reviews(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM reviews WHERE is_featured = 1 ORDER BY id DESC")
    return cursor.fetchall()

@app.post("/api/reviews")
async def create_review(request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    cursor = db.cursor()
    cursor.execute("INSERT INTO reviews (customer_name, rating, text, is_featured) VALUES (?, ?, ?, ?)",
                   (data.get("customer_name"), data.get("rating"), data.get("text"), 1 if data.get("is_featured") else 0))
    db.commit()
    return Response(content=json.dumps({"message": "Review created", "id": cursor.lastrowid}), status_code=201, media_type="application/json")

@app.put("/api/reviews/{review_id}")
async def update_review(review_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    cursor = db.cursor()
    cursor.execute("UPDATE reviews SET customer_name = ?, rating = ?, text = ?, is_featured = ? WHERE id = ?",
                   (data.get("customer_name"), data.get("rating"), data.get("text"), 1 if data.get("is_featured") else 0, review_id))
    db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"message": "Review updated successfully"}

@app.delete("/api/reviews/{review_id}")
def delete_review(review_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM reviews WHERE id = ?", (review_id,))
    db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Review not found")
    return {"message": "Review deleted successfully"}

# --- BANNERS API ---

@app.get("/api/banners")
def get_banners(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM banners ORDER BY id DESC")
    return cursor.fetchall()

@app.get("/api/banners/active")
def get_active_banners(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM banners WHERE is_approved = 1 ORDER BY id DESC")
    return cursor.fetchall()

@app.post("/api/banners")
async def create_banner(image: UploadFile = File(...), db: sqlite3.Connection = Depends(get_db)):
    image_url = save_upload_file(image)
    cursor = db.cursor()
    cursor.execute("INSERT INTO banners (image, is_approved) VALUES (?, 0)", (image_url,))
    db.commit()
    return Response(content=json.dumps({"message": "Banner uploaded", "id": cursor.lastrowid, "image": image_url}), status_code=201, media_type="application/json")

@app.put("/api/banners/{banner_id}")
async def update_banner(banner_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    cursor = db.cursor()
    cursor.execute("UPDATE banners SET is_approved = ? WHERE id = ?", (1 if data.get("is_approved") else 0, banner_id))
    db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Banner not found")
    return {"message": "Banner updated successfully"}

@app.delete("/api/banners/{banner_id}")
def delete_banner(banner_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM banners WHERE id = ?", (banner_id,))
    db.commit()
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Banner not found")
    return {"message": "Banner deleted successfully"}

# --- NOTIFICATIONS API ---

@app.get("/api/admin/notifications")
def get_admin_notifications(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM notifications ORDER BY created_at DESC")
    return cursor.fetchall()

@app.get("/api/notifications")
def get_active_notifications(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM notifications WHERE is_active = 1 ORDER BY created_at DESC")
    return cursor.fetchall()

@app.get("/api/user/notifications")
def get_user_notifications(email: str, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM user_notifications WHERE userEmail = ? ORDER BY created_at DESC", (email,))
    return cursor.fetchall()

@app.post("/api/admin/notifications")
async def create_notification(request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    cursor = db.cursor()
    cursor.execute("INSERT INTO notifications (text, is_active) VALUES (?, ?)", (data.get("text"), 1 if data.get("is_active") else 0))
    db.commit()
    
    # Send FCM push notification to all devices if it is active
    if data.get("is_active"):
        try:
            cursor.execute("SELECT token FROM device_tokens")
            tokens = [row['token'] for row in cursor.fetchall()]
            if tokens and firebase_admin._apps:
                message = messaging.MulticastMessage(
                    notification=messaging.Notification(
                        title="Taja Cart Update",
                        body=data.get("text")
                    ),
                    tokens=tokens,
                )
                response = messaging.send_each_for_multicast(message)
                print(f"Successfully sent {response.success_count} FCM messages")
        except Exception as e:
            print(f"Failed to send FCM push notification: {e}")

    return {"id": cursor.lastrowid, "text": data.get("text"), "is_active": 1 if data.get("is_active") else 0}

@app.post("/api/device-tokens")
async def register_device_token(request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    token = data.get("token")
    role = data.get("role", "customer")
    identifier = data.get("identifier")
    if not token:
        raise HTTPException(status_code=400, detail="Token is required")
    
    cursor = db.cursor()
    try:
        cursor.execute(
            "INSERT INTO device_tokens (token, role, identifier) VALUES (?, ?, ?) ON CONFLICT(token) DO UPDATE SET role=excluded.role, identifier=excluded.identifier",
            (token, role, identifier)
        )
        db.commit()
        return {"success": True, "message": "Token registered"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/admin/notifications/{notif_id}")
async def update_notification(notif_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    cursor = db.cursor()
    cursor.execute("UPDATE notifications SET text = ?, is_active = ? WHERE id = ?", (data.get("text"), 1 if data.get("is_active") else 0, notif_id))
    db.commit()
    return {"id": notif_id, "text": data.get("text"), "is_active": 1 if data.get("is_active") else 0}

@app.delete("/api/admin/notifications/{notif_id}")
def delete_notification(notif_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM notifications WHERE id = ?", (notif_id,))
    db.commit()
    return {"success": True}

# --- INVENTORY API (Categories & Products) ---

@app.get("/api/main-categories")
def get_main_categories(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM main_categories ORDER BY id ASC")
    return cursor.fetchall()

@app.post("/api/main-categories")
async def create_main_category(name: str = Form(...), image: Optional[UploadFile] = File(None), db: sqlite3.Connection = Depends(get_db)):
    image_url = save_upload_file(image) if image and image.filename else ""
    cursor = db.cursor()
    cursor.execute("INSERT INTO main_categories (name, image) VALUES (?, ?)", (name, image_url))
    db.commit()
    return {"id": cursor.lastrowid, "name": name, "image": image_url}

@app.put("/api/main-categories/{main_category_id}")
async def update_main_category(main_category_id: int, name: str = Form(...), image: Optional[UploadFile] = File(None), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    if image and image.filename:
        image_url = save_upload_file(image)
        cursor.execute("UPDATE main_categories SET name = ?, image = ? WHERE id = ?", (name, image_url, main_category_id))
        db.commit()
        return {"id": main_category_id, "name": name, "image": image_url}
    else:
        cursor.execute("UPDATE main_categories SET name = ? WHERE id = ?", (name, main_category_id))
        db.commit()
        return {"id": main_category_id, "name": name}

@app.delete("/api/main-categories/{main_category_id}")
def delete_main_category(main_category_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM main_categories WHERE id = ?", (main_category_id,))
    db.commit()
    return {"success": True}

@app.get("/api/categories")
def get_categories(mainCategoryId: Optional[int] = None, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    if mainCategoryId is not None:
        cursor.execute("SELECT * FROM categories WHERE main_category_id = ? ORDER BY id ASC", (mainCategoryId,))
    else:
        cursor.execute("SELECT * FROM categories ORDER BY id ASC")
    return cursor.fetchall()

@app.post("/api/categories")
async def create_category(main_category_id: int = Form(...), parent_category_id: Optional[int] = Form(None), name: str = Form(...), image: Optional[UploadFile] = File(None), db: sqlite3.Connection = Depends(get_db)):
    image_url = save_upload_file(image) if image and image.filename else ""
    cursor = db.cursor()
    cursor.execute("INSERT INTO categories (main_category_id, parent_category_id, name, image) VALUES (?, ?, ?, ?)", (main_category_id, parent_category_id, name, image_url))
    db.commit()
    return {"id": cursor.lastrowid, "main_category_id": main_category_id, "parent_category_id": parent_category_id, "name": name, "image": image_url}

@app.put("/api/categories/{category_id}")
async def update_category(category_id: int, main_category_id: int = Form(...), parent_category_id: Optional[int] = Form(None), name: str = Form(...), image: Optional[UploadFile] = File(None), db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    if image and image.filename:
        image_url = save_upload_file(image)
        cursor.execute("UPDATE categories SET main_category_id = ?, parent_category_id = ?, name = ?, image = ? WHERE id = ?", (main_category_id, parent_category_id, name, image_url, category_id))
        db.commit()
        return {"id": category_id, "main_category_id": main_category_id, "parent_category_id": parent_category_id, "name": name, "image": image_url}
    else:
        cursor.execute("UPDATE categories SET main_category_id = ?, parent_category_id = ?, name = ? WHERE id = ?", (main_category_id, parent_category_id, name, category_id))
        db.commit()
        return {"id": category_id, "main_category_id": main_category_id, "parent_category_id": parent_category_id, "name": name}

@app.delete("/api/categories/{category_id}")
def delete_category(category_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    db.commit()
    return {"success": True}

@app.get("/api/products")
def get_products(categoryId: Optional[int] = None, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    if categoryId is not None:
        cursor.execute("SELECT * FROM products WHERE category_id = ? ORDER BY id DESC", (categoryId,))
    else:
        cursor.execute("SELECT * FROM products ORDER BY id DESC")
    return cursor.fetchall()

@app.post("/api/products")
async def create_product(
    category_id: int = Form(...),
    name: str = Form(...),
    quantity: str = Form(...),
    sizes: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    currentPrice: float = Form(...),
    cutPrice: float = Form(...),
    rating: float = Form(...),
    in_stock: int = Form(1),
    image: Optional[List[UploadFile]] = File(None),
    db: sqlite3.Connection = Depends(get_db)
):
    image_url = ""
    add_imgs = []
    
    if image and len(image) > 0 and image[0].filename:
        image_url = save_upload_file(image[0]) or ""
        for img in image[1:]:
            if img.filename:
                path = save_upload_file(img)
                if path:
                    add_imgs.append(path)
                    
    add_imgs_json = json.dumps(add_imgs)

    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO products (category_id, name, quantity, sizes, gender, currentPrice, cutPrice, rating, in_stock, image, additional_images) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (category_id, name, quantity, sizes, gender, currentPrice, cutPrice, rating, in_stock, image_url, add_imgs_json)
    )
    db.commit()
    return {"id": cursor.lastrowid, "category_id": category_id, "name": name, "quantity": quantity, "sizes": sizes, "gender": gender,
            "currentPrice": currentPrice, "cutPrice": cutPrice, "rating": rating, "in_stock": in_stock, "image": image_url, "additional_images": add_imgs_json}

@app.put("/api/products/{product_id}")
async def update_product(
    product_id: int,
    category_id: int = Form(...),
    name: str = Form(...),
    quantity: str = Form(...),
    sizes: Optional[str] = Form(None),
    gender: Optional[str] = Form(None),
    currentPrice: float = Form(...),
    cutPrice: float = Form(...),
    rating: float = Form(...),
    in_stock: int = Form(1),
    image: Optional[List[UploadFile]] = File(None),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    
    updates = [
        "category_id = ?", "name = ?", "quantity = ?", "sizes = ?", "gender = ?", 
        "currentPrice = ?", "cutPrice = ?", "rating = ?", "in_stock = ?"
    ]
    params = [category_id, name, quantity, sizes, gender, currentPrice, cutPrice, rating, in_stock]
    
    image_url = None
    add_imgs_json = None
    
    if image and len(image) > 0 and image[0].filename:
        image_url = save_upload_file(image[0])
        updates.append("image = ?")
        params.append(image_url)
        
        add_imgs = []
        for img in image[1:]:
            if img.filename:
                path = save_upload_file(img)
                if path:
                    add_imgs.append(path)
        add_imgs_json = json.dumps(add_imgs)
        updates.append("additional_images = ?")
        params.append(add_imgs_json)

    updates_str = ", ".join(updates)
    params.append(product_id)
    
    cursor.execute(f"UPDATE products SET {updates_str} WHERE id = ?", tuple(params))
    db.commit()
    
    res = {"id": product_id, "category_id": category_id, "name": name, "quantity": quantity, "sizes": sizes, "gender": gender,
            "currentPrice": currentPrice, "cutPrice": cutPrice, "rating": rating, "in_stock": in_stock}
    if image_url is not None: res["image"] = image_url
    if add_imgs_json is not None: res["additional_images"] = add_imgs_json
    return res

@app.delete("/api/products/{product_id}")
def delete_product(product_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
    db.commit()
    return {"success": True}

# --- DEALS OF THE DAY API ---

@app.get("/api/deals")
def get_deals(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT * FROM deals_of_the_day ORDER BY id DESC")
    return cursor.fetchall()

@app.post("/api/deals")
async def create_deal(
    name: str = Form(...),
    quantity: str = Form(...),
    currentPrice: float = Form(...),
    cutPrice: float = Form(...),
    rating: float = Form(...),
    in_stock: int = Form(1),
    image: Optional[UploadFile] = File(None),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM deals_of_the_day")
    if cursor.fetchone()['count'] >= 10:
        raise HTTPException(status_code=400, detail="Maximum 10 deals allowed")

    image_url = save_upload_file(image) if image and image.filename else ""
    cursor.execute(
        "INSERT INTO deals_of_the_day (name, quantity, currentPrice, cutPrice, rating, in_stock, image) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, quantity, currentPrice, cutPrice, rating, in_stock, image_url)
    )
    db.commit()
    return {"id": cursor.lastrowid, "name": name, "quantity": quantity, 
            "currentPrice": currentPrice, "cutPrice": cutPrice, "rating": rating, "in_stock": in_stock, "image": image_url}

@app.put("/api/deals/{deal_id}")
async def update_deal(
    deal_id: int,
    name: str = Form(...),
    quantity: str = Form(...),
    currentPrice: float = Form(...),
    cutPrice: float = Form(...),
    rating: float = Form(...),
    in_stock: int = Form(1),
    image: Optional[UploadFile] = File(None),
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    if image and image.filename:
        image_url = save_upload_file(image)
        cursor.execute(
            "UPDATE deals_of_the_day SET name = ?, quantity = ?, currentPrice = ?, cutPrice = ?, rating = ?, in_stock = ?, image = ? WHERE id = ?",
            (name, quantity, currentPrice, cutPrice, rating, in_stock, image_url, deal_id)
        )
        db.commit()
        return {"id": deal_id, "name": name, "quantity": quantity, 
                "currentPrice": currentPrice, "cutPrice": cutPrice, "rating": rating, "in_stock": in_stock, "image": image_url}
    else:
        cursor.execute(
            "UPDATE deals_of_the_day SET name = ?, quantity = ?, currentPrice = ?, cutPrice = ?, rating = ?, in_stock = ? WHERE id = ?",
            (name, quantity, currentPrice, cutPrice, rating, in_stock, deal_id)
        )
        db.commit()
        return {"id": deal_id, "name": name, "quantity": quantity, 
                "currentPrice": currentPrice, "cutPrice": cutPrice, "rating": rating, "in_stock": in_stock}

@app.delete("/api/deals/{deal_id}")
def delete_deal(deal_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("DELETE FROM deals_of_the_day WHERE id = ?", (deal_id,))
    db.commit()
    return {"success": True}

# --- UNIFIED HOME FEED API ---

@app.get("/api/home-feed")
def get_home_feed(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    
    cursor.execute("SELECT * FROM main_categories ORDER BY id ASC")
    main_categories = cursor.fetchall()
    
    cursor.execute("SELECT * FROM categories ORDER BY id ASC")
    categories = cursor.fetchall()
    
    cursor.execute("SELECT * FROM products ORDER BY id DESC")
    products = cursor.fetchall()
    
    cursor.execute("SELECT * FROM deals_of_the_day ORDER BY id DESC")
    deals = cursor.fetchall()
    
    cursor.execute("SELECT * FROM offers ORDER BY valid_until DESC")
    offers = cursor.fetchall()
    
    cursor.execute("SELECT * FROM settings")
    settings = cursor.fetchall()
    
    cursor.execute("SELECT * FROM announcements")
    announcements = cursor.fetchall()
    
    cursor.execute("SELECT * FROM reviews WHERE is_featured = 1 ORDER BY id DESC")
    reviews = cursor.fetchall()
    
    cursor.execute("SELECT * FROM banners WHERE is_approved = 1 ORDER BY id DESC")
    banners = cursor.fetchall()
    
    cursor.execute("SELECT * FROM hubs ORDER BY id DESC")
    hubs = cursor.fetchall()
    
    cursor.execute("SELECT * FROM notifications WHERE is_active = 1 ORDER BY created_at DESC")
    notifications = cursor.fetchall()
    
    return {
        "main_categories": main_categories,
        "categories": categories,
        "products": products,
        "deals": deals,
        "offers": offers,
        "settings": settings,
        "announcements": announcements,
        "reviews": reviews,
        "banners": banners,
        "hubs": hubs,
        "notifications": notifications
    }


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
        if existing.get("is_deleted") == 1:
            raise HTTPException(status_code=403, detail="Your account has been permanently deleted.")
            
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
        return get_dp_with_true_rating(cursor, new_id)

@app.get("/api/delivery/orders/{email}")
def get_delivery_orders(email: str, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT id, is_disabled, is_deleted FROM delivery_personnel WHERE email = ?", (email,))
    dp = cursor.fetchone()
    if not dp or dp.get("is_deleted") == 1:
        raise HTTPException(status_code=404, detail="Delivery personnel not found")
        
    if dp.get("is_disabled") == 1:
        return []
    
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
    review = data.get("review")
    
    if not rating:
        raise HTTPException(status_code=400, detail="Rating is required")
        
    cursor = db.cursor()
    cursor.execute("UPDATE orders SET delivery_partner_rating = ?, delivery_partner_review = ? WHERE id = ?", (rating, review, order_id))
    
    cursor.execute("SELECT delivery_partner_id FROM orders WHERE id = ?", (order_id,))
    order = cursor.fetchone()
    if order and order["delivery_partner_id"]:
        dp_id = order["delivery_partner_id"]
        true_dp = get_dp_with_true_rating(cursor, dp_id)
        if true_dp:
            cursor.execute("UPDATE delivery_personnel SET rating = ?, total_ratings = ? WHERE id = ?", (true_dp['rating'], true_dp['total_ratings'], dp_id))
            
    db.commit()
    return {"message": "Delivery rated successfully", "id": order_id, "rating": rating, "review": review}

@app.get("/api/delivery-personnel/{dp_id}")
def get_delivery_personnel(dp_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    dp = get_dp_with_true_rating(cursor, dp_id)
    if not dp:
        raise HTTPException(status_code=404, detail="Delivery personnel not found")
    return dp

@app.put("/api/delivery-personnel/{dp_id}")
async def update_delivery_personnel(dp_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    name = data.get("name")
    phone = data.get("phone")
    
    if not name or not phone:
        raise HTTPException(status_code=400, detail="Name and phone are required")
        
    cursor = db.cursor()
    cursor.execute("UPDATE delivery_personnel SET name = ?, phone = ? WHERE id = ?", (name, phone, dp_id))
    db.commit()
    
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Delivery personnel not found")
        
    return get_dp_with_true_rating(cursor, dp_id)

@app.get("/api/delivery-personnel/hub/{hub_id}")
def get_delivery_personnel_by_hub(hub_id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT id FROM delivery_personnel WHERE hub_id = ? AND is_active = 1", (hub_id,))
    dp_ids = [row["id"] for row in cursor.fetchall()]
    dps = []
    for dp_id in dp_ids:
        dp = get_dp_with_true_rating(cursor, dp_id)
        if dp:
            dps.append(dp)
    return dps

@app.patch("/api/orders/{order_id}/assign")
async def assign_order_manually(order_id: str, request: Request, db: sqlite3.Connection = Depends(get_db)):
    data = await request.json()
    dp_id = data.get("delivery_partner_id")
    if not dp_id:
        raise HTTPException(status_code=400, detail="delivery_partner_id is required")
        
    cursor = db.cursor()
    # verify dp exists
    cursor.execute("SELECT id FROM delivery_personnel WHERE id = ?", (dp_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Delivery personnel not found")
        
    # get current assigned dp
    cursor.execute("SELECT delivery_partner_id FROM orders WHERE id = ?", (order_id,))
    order_row = cursor.fetchone()
    if not order_row:
        raise HTTPException(status_code=404, detail="Order not found")
    
    old_dp_id = order_row["delivery_partner_id"]
        
    cursor.execute("UPDATE orders SET delivery_partner_id = ? WHERE id = ?", (dp_id, order_id))
    db.commit()
    
    # Trigger Push Notification to Delivery Partner
    try:
        import firebase_admin
        from firebase_admin import messaging
        
        # Notify new DP
        cursor.execute("SELECT email FROM delivery_personnel WHERE id=?", (dp_id,))
        dp_row = cursor.fetchone()
        if dp_row:
            dp_email = dp_row['email']
            cursor.execute("SELECT token FROM device_tokens WHERE identifier=? AND role='delivery'", (dp_email,))
            dp_tokens = [r['token'] for r in cursor.fetchall()]
            if dp_tokens and firebase_admin._apps:
                fcm_msg = messaging.MulticastMessage(
                    notification=messaging.Notification(
                        title="New Delivery Assigned! 📦",
                        body="An admin manually assigned an order to you. Please open the app to check."
                    ),
                    tokens=dp_tokens,
                )
                messaging.send_each_for_multicast(fcm_msg)
                
        # Notify old DP if reassigned
        if old_dp_id and old_dp_id != dp_id:
            cursor.execute("SELECT email FROM delivery_personnel WHERE id=?", (old_dp_id,))
            old_dp_row = cursor.fetchone()
            if old_dp_row:
                old_dp_email = old_dp_row['email']
                cursor.execute("SELECT token FROM device_tokens WHERE identifier=? AND role='delivery'", (old_dp_email,))
                old_dp_tokens = [r['token'] for r in cursor.fetchall()]
                if old_dp_tokens and firebase_admin._apps:
                    fcm_msg_old = messaging.MulticastMessage(
                        notification=messaging.Notification(
                            title="Order Re-assigned 🔄",
                            body=f"Order #{order_id} has been re-assigned to another delivery partner."
                        ),
                        tokens=old_dp_tokens,
                    )
                    messaging.send_each_for_multicast(fcm_msg_old)
    except Exception as e:
        print(f"Failed to send FCM push to delivery partner: {e}")
        
    return {"message": "Order assigned successfully"}

@app.patch("/api/admin/delivery-personnel/{id}/toggle-status")
def toggle_dp_status(id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT is_disabled FROM delivery_personnel WHERE id = ?", (id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Delivery personnel not found")
    
    new_status = 0 if row["is_disabled"] else 1
    cursor.execute("UPDATE delivery_personnel SET is_disabled = ? WHERE id = ?", (new_status, id))
    db.commit()
    return {"message": "Status updated", "is_disabled": new_status}

@app.delete("/api/admin/delivery-personnel/{id}")
def delete_dp(id: int, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("UPDATE delivery_personnel SET is_deleted = 1, is_disabled = 1 WHERE id = ?", (id,))
    db.commit()
    return {"message": "Delivery personnel permanently deleted"}

@app.get("/api/admin/delivery-partners/performance")
def get_delivery_partners_performance(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    hub_id: Optional[int] = None,
    is_deleted: Optional[int] = 0,
    db: sqlite3.Connection = Depends(get_db)
):
    cursor = db.cursor()
    
    # Base query for delivery personnel
    query = "SELECT dp.*, h.name as hub_name FROM delivery_personnel dp LEFT JOIN hubs h ON dp.hub_id = h.id WHERE dp.is_deleted = ?"
    params = [1 if is_deleted == 1 else 0]
    if hub_id:
        query += " AND dp.hub_id = ?"
        params.append(hub_id)
        
    cursor.execute(query, tuple(params))
    dps = [dict(row) for row in cursor.fetchall()]
    
    for dp in dps:
        dp_id = dp["id"]
        
        # Get active orders
        cursor.execute("SELECT id, status, date FROM orders WHERE delivery_partner_id = ? AND status NOT IN ('Delivered', 'Cancelled')", (dp_id,))
        dp["active_orders"] = [dict(row) for row in cursor.fetchall()]
        dp["status"] = "Busy" if len(dp["active_orders"]) > 0 else "Free"
        
        # Get delivered orders
        del_query = "SELECT id, status, date, grandTotal, delivery_partner_rating, delivery_partner_review FROM orders WHERE delivery_partner_id = ? AND status = 'Delivered'"
        cursor.execute(del_query, (dp_id,))
        all_del_orders = [dict(row) for row in cursor.fetchall()]
        
        filtered_del_orders = []
        if start_date or end_date:
            from datetime import datetime
            
            try:
                start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
                end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None
                if end_dt:
                    end_dt = end_dt.replace(hour=23, minute=59, second=59)
            except Exception:
                start_dt = None
                end_dt = None
                
            for order in all_del_orders:
                # Format is like "21 Aug 2026, 06:16 am" or "14 Aug 2026 at 06:11 AM"
                date_str = order['date'].replace(" at ", ", ")
                try:
                    order_dt = datetime.strptime(date_str, "%d %b %Y, %I:%M %p")
                    if start_dt and order_dt < start_dt:
                        continue
                    if end_dt and order_dt > end_dt:
                        continue
                    filtered_del_orders.append(order)
                except Exception:
                    # If we can't parse it, just append it so we don't lose data
                    filtered_del_orders.append(order)
            dp["delivered_orders"] = filtered_del_orders
        else:
            dp["delivered_orders"] = all_del_orders
            
        dp["delivered_orders"].sort(key=lambda x: x['date'], reverse=True)
        dp["delivered_count"] = len(dp["delivered_orders"])
        
    return dps
