import sqlite3, os
conn = sqlite3.connect('/home/pmoraga/hipocrafy-edge/edge_data.db')
conn.execute("UPDATE local_studies SET sync_status='failed'")
conn.commit()
conn.close()
