import sys

with open('main.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_block = """    if user_lat is not None and user_lng is not None:
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
            assigned_delivery_id = dp_row["id"]"""

new_block = """    if user_lat is not None and user_lng is not None:
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
            # Find delivery personnel in the nearest hub only, ordered by number of active orders
            query = f'''
                SELECT dp.id, COUNT(o.id) as active_orders 
                FROM delivery_personnel dp
                LEFT JOIN orders o ON dp.id = o.delivery_partner_id AND o.status NOT IN ('Delivered', 'Cancelled')
                WHERE dp.hub_id = {nearest_hub_id} AND dp.is_active = 1
                GROUP BY dp.id
                ORDER BY active_orders ASC, dp.id ASC
                LIMIT 1
            '''
            cursor.execute(query)
            dp_row = cursor.fetchone()
            if dp_row:
                assigned_delivery_id = dp_row["id"]"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open('main.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Successfully updated assignment logic.")
else:
    print("Could not find the old block. Maybe it has different formatting.")
