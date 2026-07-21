import sqlite3
conn = sqlite3.connect('/home/pmoraga/hipocrafy-edge/edge_data.db')
try:
    conn.execute('ALTER TABLE local_studies ADD COLUMN retry_count INTEGER DEFAULT 0')
    print('Columna añadida')
except Exception as e:
    print(e)
conn.commit()
conn.close()
