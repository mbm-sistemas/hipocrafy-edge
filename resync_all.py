import sys
import os
import json
import sqlite3
sys.path.append('/home/pmoraga/hipocrafy-edge')
from sync_service import upload_ai_result

DB_PATH = '/home/pmoraga/hipocrafy-edge/edge_data.db'

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM local_studies WHERE sync_status='failed' OR sync_status='pending'").fetchall()
    
    print(f"Encontrados {len(rows)} estudios para re-sincronizar.")
    
    success_count = 0
    fail_count = 0
    
    for row in rows:
        uid = row['study_instance_uid']
        findings = json.loads(row['ai_findings'] or "{}")
        dni = row['patient_dni']
        specialty = findings.get('specialty')
        
        try:
            success = upload_ai_result(
                orthanc_study_uid=uid,
                report=findings.get("report", ""),
                ai_data=findings,
                patient_dni=dni,
                specialty=specialty
            )
            
            if success:
                conn.execute("UPDATE local_studies SET sync_status='synced' WHERE study_instance_uid=?", (uid,))
                conn.commit()
                success_count += 1
                if success_count % 10 == 0:
                    print(f"Synced {success_count} studies...")
            else:
                fail_count += 1
        except Exception as e:
            print(f"Error procesando {uid}: {e}")
            fail_count += 1

    print(f"Finalizado. Exitosos: {success_count}. Fallidos: {fail_count}.")
    conn.close()

if __name__ == '__main__':
    main()
