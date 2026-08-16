import sys
import os

filepath = "main.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

new_api = """
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
        
    cursor.execute("SELECT * FROM delivery_personnel WHERE id = ?", (dp_id,))
    return dict(cursor.fetchone())
"""

content += new_api

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
print("Successfully appended PUT /api/delivery-personnel/{dp_id}")
