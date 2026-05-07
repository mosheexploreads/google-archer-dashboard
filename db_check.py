import sqlite3

conn = sqlite3.connect("ads_dashboard.db")
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cur.fetchall()
print("Tables:", tables)

for (table,) in tables:
    cur.execute(f"SELECT MIN(date), MAX(date), COUNT(*), COUNT(DISTINCT asin) FROM {table}")
    row = cur.fetchone()
    print(f"\n{table}: min={row[0]}, max={row[1]}, rows={row[2]}, asins={row[3]}")

conn.close()
