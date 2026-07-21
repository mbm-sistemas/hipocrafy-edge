import sqlite3
conn = sqlite3.connect('/home/pmoraga/hipocrafy-edge/edge_data.db')
print(conn.execute("SELECT sync_status, count(*) FROM local_studies GROUP BY sync_status").fetchall())
