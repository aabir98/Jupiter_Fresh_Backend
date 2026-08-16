import sqlite3
db = sqlite3.connect('taja_cart.db')
try:
    db.execute('ALTER TABLE device_tokens ADD COLUMN role TEXT DEFAULT "customer"')
    db.commit()
    print('Added role column')
except Exception as e:
    print(e)
