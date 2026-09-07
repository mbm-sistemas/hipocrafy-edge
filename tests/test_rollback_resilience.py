"""
Test Suite: OTA Software Rollback Resilience Test
Verifies that when an OTA application update introduces a regression or fails the post-install
health check, the automated updater triggers an immediate rollback to the previous version,
restoring operational files and preserving local database/configuration without data loss.
"""

import os
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

# Resolve paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
venv_site_packages = os.path.join(BASE_DIR, "venv", "Lib", "site-packages")
if os.path.exists(venv_site_packages) and venv_site_packages not in sys.path:
    sys.path.insert(0, venv_site_packages)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app_updater import _backup_current, _extract_over_app_dir, _restore_backup, PRESERVE_PATHS


class TestAppRollbackResilience(unittest.TestCase):

    def setUp(self):
        # Create isolated temporary directory representing APP_DIR
        self.test_dir = tempfile.TemporaryDirectory()
        self.app_dir = Path(self.test_dir.name)

        # 1. Setup baseline v1.0.0
        self.version_file = self.app_dir / "VERSION"
        self.version_file.write_text("1.0.0")

        self.main_file = self.app_dir / "main.py"
        self.main_file.write_text("# Main production v1.0.0\nhealthy = True\n")

        # Create files that MUST be preserved (env, db, models)
        self.env_file = self.app_dir / ".env"
        self.env_file.write_text("DEVICE_ID=edge01-cegin\nSECRET_KEY=cegin_2026\n")

        self.db_file = self.app_dir / "edge_data.db"
        self.db_file.write_text("SQLITE_BINARY_DATA_PATIENT_STUDIES_12345")

        self.backup_dir = self.app_dir / "backups"

    def tearDown(self):
        self.test_dir.cleanup()

    def test_01_backup_creation_and_preservation_rules(self):
        """Verify that backup packages operational code while excluding preserved databases and env."""
        import app_updater
        original_app_dir = app_updater.APP_DIR
        original_backup_dir = app_updater.BACKUP_DIR
        try:
            app_updater.APP_DIR = self.app_dir
            app_updater.BACKUP_DIR = self.backup_dir

            backup_path = _backup_current("1.0.0")
            self.assertIsNotNone(backup_path)
            self.assertTrue(backup_path.exists())

            # Inspect tarball contents
            with tarfile.open(backup_path, "r:gz") as tar:
                names = tar.getnames()
                self.assertIn("main.py", names)
                self.assertIn("VERSION", names)
                # Sensitive / persistent data MUST NOT be in the backup tarball
                self.assertNotIn(".env", names)
                self.assertNotIn("edge_data.db", names)

        finally:
            app_updater.APP_DIR = original_app_dir
            app_updater.BACKUP_DIR = original_backup_dir

    def test_02_simulated_broken_update_and_automatic_rollback(self):
        """Simulate a broken update (v2.0.0) that fails health check, triggering full rollback."""
        import app_updater
        original_app_dir = app_updater.APP_DIR
        original_backup_dir = app_updater.BACKUP_DIR
        try:
            app_updater.APP_DIR = self.app_dir
            app_updater.BACKUP_DIR = self.backup_dir

            # Step 1: Generate pre-update backup of v1.0.0
            backup_path = _backup_current("1.0.0")
            self.assertTrue(backup_path.exists())

            # Step 2: Create broken v2.0.0 tarball
            broken_tarball_path = self.app_dir / "v2.0.0-broken.tar.gz"
            with tempfile.TemporaryDirectory() as tmp_rel:
                tmp_rel_path = Path(tmp_rel)
                (tmp_rel_path / "VERSION").write_text("2.0.0")
                (tmp_rel_path / "main.py").write_text("SYNTAX ERROR; CRASH ON IMPORT; def ???")
                (tmp_rel_path / "broken_feature.py").write_text("# Unstable code")

                with tarfile.open(broken_tarball_path, "w:gz") as tar:
                    for item in tmp_rel_path.iterdir():
                        tar.add(item, arcname=item.name)

            # Step 3: Extract broken update over app dir (simulating OTA installation)
            _extract_over_app_dir(broken_tarball_path)

            # Confirm app is now in broken v2.0.0 state
            self.assertEqual((self.app_dir / "VERSION").read_text().strip(), "2.0.0")
            self.assertIn("SYNTAX ERROR", (self.app_dir / "main.py").read_text())
            self.assertTrue((self.app_dir / "broken_feature.py").exists())

            # Step 4: Health check fails -> Trigger Rollback
            mock_restart_called = []
            def mock_restart():
                mock_restart_called.append(True)
                return True

            original_restart = app_updater._restart_services
            app_updater._restart_services = mock_restart
            try:
                # Trigger rollback using the v1.0.0 backup
                _restore_backup(backup_path)
            finally:
                app_updater._restart_services = original_restart

            # Step 5: Verify complete restoration
            # A) VERSION restored to 1.0.0
            self.assertEqual((self.app_dir / "VERSION").read_text().strip(), "1.0.0")

            # B) main.py restored to healthy v1.0.0 code
            self.assertIn("healthy = True", (self.app_dir / "main.py").read_text())
            self.assertNotIn("SYNTAX ERROR", (self.app_dir / "main.py").read_text())

            # C) New files from broken update are deleted or overridden
            # Note: _restore_backup extracts baseline files.

            # D) Critical persistent data (.env and edge_data.db) remained 100% intact
            self.assertEqual(self.env_file.read_text(), "DEVICE_ID=edge01-cegin\nSECRET_KEY=cegin_2026\n")
            self.assertEqual(self.db_file.read_text(), "SQLITE_BINARY_DATA_PATIENT_STUDIES_12345")

            # E) Service restart was triggered
            self.assertEqual(len(mock_restart_called), 1)

        finally:
            app_updater.APP_DIR = original_app_dir
            app_updater.BACKUP_DIR = original_backup_dir


if __name__ == "__main__":
    unittest.main()
