import sqlite3
import os

DB_PATH = 'edge_data.db'

def reset():
    if not os.path.exists(DB_PATH):
        print("La base de datos del Edge no existe en este directorio.")
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("Borrando estudios locales del Edge...")
    try:
        cursor.execute("DELETE FROM local_studies;")
        conn.commit()
        print("✅ Reseteo completado en el Edge local.")
    except Exception as e:
        print(f"Error reseteando tablas: {e}")
    finally:
        conn.close()

if __name__ == '__main__':
    reset()
