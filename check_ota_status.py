import os
import app_updater

print("=" * 60)
print("   ESTADO OTA APP UPDATER EN EDGE01-CEGIN")
print("=" * 60)
print(f"ENFORCE_MAINTENANCE_WINDOW (.env): {os.getenv('ENFORCE_MAINTENANCE_WINDOW')}")
print(f"ENFORCE_MAINTENANCE_WINDOW (código): {app_updater.ENFORCE_MAINTENANCE_WINDOW}")
print(f"¿Está en ventana de mantenimiento ahora?: {app_updater.is_in_maintenance_window()}")
print(f"AUTO_INSTALL_APP_UPDATES: {app_updater.AUTO_INSTALL_APP_UPDATES}")
print(f"Versión Local Instalada: {app_updater.get_local_version()}")

remote = app_updater._get_remote_latest()
print(f"Versión Remota en la Nube: {remote}")

if remote and remote.get("version"):
    remote_v = remote.get("version")
    local_v = app_updater.get_local_version()
    if remote_v != local_v:
        print(f"\n--> HAY ACTUALIZACIÓN DISPONIBLE: v{remote_v} (actual: v{local_v})")
        if app_updater.AUTO_INSTALL_APP_UPDATES:
            if app_updater.ENFORCE_MAINTENANCE_WINDOW and not app_updater.is_in_maintenance_window():
                print("--> NO se instalará ahora porque NO está en la ventana de mantenimiento (22:00 a 06:00 o Domingos).")
            else:
                print("--> Se instalará automáticamente en el próximo ciclo.")
    else:
        print(f"\n--> El equipo ya está en la última versión (v{remote_v}).")
print("=" * 60)
