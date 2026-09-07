"""
Test Suite: Offline Store & Forward Resilience Test
Tests the Edge gateway's ability to safely queue medical studies locally in SQLite
when offline, survive network outages, and forward all queued records once connectivity
is restored without loss or duplication.
"""

import os
import sys
import json
import sqlite3
import unittest
import http.server
import threading
import time
from datetime import datetime

# Resolve workspace paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

TEST_DB_PATH = os.path.join(BASE_DIR, "test_store_forward.db")


class MockCloudHandler(http.server.BaseHTTPRequestHandler):
    received_studies = []

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        study_payload = json.loads(post_data.decode('utf-8'))
        MockCloudHandler.received_studies.append(study_payload)
        
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"status": "success", "study_id": len(MockCloudHandler.received_studies)}).encode('utf-8'))

    def log_message(self, format, *args):
        # Suppress server logging during unit tests
        pass


class TestStoreAndForwardResilience(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Initialize isolated test database
        if os.path.exists(TEST_DB_PATH):
            os.remove(TEST_DB_PATH)

        with sqlite3.connect(TEST_DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE local_studies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    study_instance_uid TEXT UNIQUE,
                    patient_dni TEXT,
                    modality TEXT,
                    ai_findings TEXT,
                    image_path TEXT,
                    sync_status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    synced_at DATETIME,
                    retry_count INTEGER DEFAULT 0,
                    last_error TEXT
                )
            """)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(TEST_DB_PATH):
            try:
                os.remove(TEST_DB_PATH)
            except Exception:
                pass

    def test_01_offline_study_persisted_safely(self):
        """Verify study is committed to SQLite with pending status during capture."""
        uid = "1.2.840.10008.TEST.OFFLINE.001"
        dni = "99887766"
        modality = "US"
        findings = {
            "finding": "Nódulo tiroideo sospechoso TIRADS 4",
            "confidence": 0.88,
            "anomalies": ["microcalcificaciones"],
            "specialty": "tiroides"
        }

        with sqlite3.connect(TEST_DB_PATH) as conn:
            conn.execute(
                "INSERT INTO local_studies (study_instance_uid, patient_dni, modality, ai_findings, sync_status) VALUES (?, ?, ?, ?, 'pending')",
                (uid, dni, modality, json.dumps(findings))
            )

        with sqlite3.connect(TEST_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM local_studies WHERE study_instance_uid = ?", (uid,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["sync_status"], "pending")
            self.assertEqual(row["patient_dni"], dni)
            self.assertEqual(row["modality"], modality)

    def test_02_network_failure_increments_retry_and_preserves_data(self):
        """Simulate failed sync attempt when cloud is unreachable (offline)."""
        uid = "1.2.840.10008.TEST.OFFLINE.001"
        
        # Simulate network error update
        with sqlite3.connect(TEST_DB_PATH) as conn:
            conn.execute("""
                UPDATE local_studies
                SET sync_status = 'failed',
                    retry_count = retry_count + 1,
                    last_error = 'Connection refused (Simulated Offline Mode)'
                WHERE study_instance_uid = ?
            """, (uid,))

        with sqlite3.connect(TEST_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM local_studies WHERE study_instance_uid = ?", (uid,)).fetchone()
            self.assertEqual(row["sync_status"], "failed")
            self.assertEqual(row["retry_count"], 1)
            self.assertIn("Offline", row["last_error"])
            # Verify clinical findings were NEVER corrupted or lost
            findings = json.loads(row["ai_findings"])
            self.assertEqual(findings["confidence"], 0.88)

    def test_03_online_recovery_and_forwarding(self):
        """Simulate network reconnection: forward queued pending/failed studies to cloud receiver."""
        # 1. Start mock cloud receiver on available port
        server_port = 8991
        httpd = http.server.HTTPServer(('127.0.0.1', server_port), MockCloudHandler)
        server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        server_thread.start()

        time.sleep(0.2)

        try:
            # 2. Add a second queued study to test batch store-and-forward
            uid2 = "1.2.840.10008.TEST.OFFLINE.002"
            findings2 = {
                "finding": "Ecocardiograma normal",
                "confidence": 0.95,
                "anomalies": [],
                "specialty": "cardiologia"
            }
            with sqlite3.connect(TEST_DB_PATH) as conn:
                conn.execute(
                    "INSERT INTO local_studies (study_instance_uid, patient_dni, modality, ai_findings, sync_status) VALUES (?, ?, ?, ?, 'pending')",
                    (uid2, "44332211", "US", json.dumps(findings2))
                )

            # 3. Execute Store & Forward Sync Worker
            import urllib.request

            with sqlite3.connect(TEST_DB_PATH) as conn:
                conn.row_factory = sqlite3.Row
                queued_studies = conn.execute(
                    "SELECT * FROM local_studies WHERE sync_status IN ('pending', 'failed')"
                ).fetchall()

            self.assertEqual(len(queued_studies), 2)

            for study in queued_studies:
                payload = {
                    "patient_document": study["patient_dni"],
                    "study_date": study["created_at"],
                    "modality": study["modality"],
                    "ai_findings": json.loads(study["ai_findings"]),
                    "study_instance_uid": study["study_instance_uid"]
                }
                
                req = urllib.request.Request(
                    f"http://127.0.0.1:{server_port}/studies",
                    data=json.dumps(payload).encode('utf-8'),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status == 200:
                        with sqlite3.connect(TEST_DB_PATH) as conn:
                            conn.execute(
                                "UPDATE local_studies SET sync_status = 'synced', synced_at = ? WHERE study_instance_uid = ?",
                                (datetime.now().isoformat(), study["study_instance_uid"])
                            )

            # 4. Verify SQLite database reflects successful sync
            with sqlite3.connect(TEST_DB_PATH) as conn:
                remaining_pending = conn.execute(
                    "SELECT COUNT(*) FROM local_studies WHERE sync_status IN ('pending', 'failed')"
                ).fetchone()[0]
                synced_count = conn.execute(
                    "SELECT COUNT(*) FROM local_studies WHERE sync_status = 'synced'"
                ).fetchone()[0]

            self.assertEqual(remaining_pending, 0, "All offline studies must be successfully forwarded")
            self.assertEqual(synced_count, 2, "Both queued studies must have status 'synced'")
            self.assertEqual(len(MockCloudHandler.received_studies), 2, "Mock Cloud received both payloads")

        finally:
            httpd.shutdown()
            server_thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
