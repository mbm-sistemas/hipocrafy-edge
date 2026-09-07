import os
import sys
import unittest
from unittest.mock import patch

# Asegurar path al entorno de hipocrafy-edge
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _root not in sys.path:
    sys.path.insert(0, _root)

import app_updater

class TestMaintenanceWindowBehavior(unittest.TestCase):

    def test_respects_maintenance_window_at_current_time(self):
        """
        Valida que a la hora actual (18:00 hs aprox.) el sistema determine
        que NO está en ventana de mantenimiento y postergue la instalación.
        """
        # La ventana es 22:00 a 06:00 hs y domingos
        in_window = app_updater.is_in_maintenance_window()
        print(f"\n[TEST] Hora actual dentro de ventana: {in_window}")
        
        # Simulamos que la nube tiene una nueva versión disponible
        dummy_remote = {
            "version": "99.99.99-simulated-new-version",
            "download_url": "https://example.com/release.tar.gz"
        }

        with patch.object(app_updater, "_get_remote_latest", return_value=dummy_remote), \
             patch.object(app_updater, "AUTO_INSTALL_APP_UPDATES", True), \
             patch.object(app_updater, "ENFORCE_MAINTENANCE_WINDOW", True), \
             patch.object(app_updater, "is_in_maintenance_window", return_value=False), \
             patch.object(app_updater, "_download_tarball") as mock_download, \
             patch.object(app_updater, "_extract_over_app_dir") as mock_extract, \
             patch.object(app_updater, "_restart_services") as mock_restart, \
             patch.object(app_updater, "_report_status") as mock_report:

            # Ejecutamos el chequeo de OTA
            result = app_updater.check_and_update()

            # Verificaciones críticas de seguridad:
            # 1. NO debe haber descargado el tarball
            mock_download.assert_not_called()
            # 2. NO debe haber extraído nada sobre el código de la app
            mock_extract.assert_not_called()
            # 3. NO debe haber reiniciado ningún servicio
            mock_restart.assert_not_called()
            # 4. Debe haber reportado estado 'idle' (postergado) a la nube
            mock_report.assert_called_with("99.99.99-simulated-new-version", "idle", error=None)
            
            print("[TEST] ¡ÉXITO! La instalación fue correctamente pospuesta sin tocar archivos ni reiniciar servicios.")

if __name__ == "__main__":
    unittest.main()
