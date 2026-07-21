import sys
sys.path.append('/home/pmoraga/hipocrafy-edge')
import sqlite3
import json
from sync_service import upload_ai_result
conn = sqlite3.connect('/home/pmoraga/hipocrafy-edge/edge_data.db')
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT * FROM local_studies WHERE sync_status='failed' LIMIT 1").fetchone()
findings = json.loads(row['ai_findings'])
print("Trying UID:", row['study_instance_uid'])
print("Organ Analysis:", findings.get('organ_analysis'))
success = upload_ai_result(row['study_instance_uid'], findings.get('report', ''), findings, row['patient_dni'], findings.get('specialty'))
print("Success:", success)
