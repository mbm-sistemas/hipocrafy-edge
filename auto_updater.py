#!/usr/bin/env python3
"""
Software Auto-Updater & Resilience Watchdog — Hipocrafy Edge

Periodic script executed by systemd timer (hipocrafy-updater.timer).
Checks remote Git repository for new code releases, applies updates,
restarts hipocrafy-edge service, and performs health check.
If the update causes a crash or health-check failure, it executes an
automatic rollback (git reset --hard) to restore service continuity.
"""

import logging
import os
import subprocess
import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [HipocrafyUpdater] %(message)s"
)
logger = logging.getLogger("HipocrafyUpdater")

EDGE_DIR = os.path.dirname(os.path.abspath(__file__))
CLOUD_URL = os.getenv("HIPOCRAFY_CLOUD_URL", "").rstrip("/")
GATEWAY_TOKEN = os.getenv("GATEWAY_API_TOKEN", "")
EDGE_PORT = os.getenv("PORT", "8080")
HEALTH_URL = f"http://127.0.0.1:{EDGE_PORT}/health"
TIMEOUT = 10


def run_cmd(cmd: str, cwd: str = EDGE_DIR) -> tuple[bool, str, str]:
    try:
        result = subprocess.run(
            cmd, shell=True, cwd=cwd, capture_output=True, text=True
        )
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except Exception as exc:
        return False, "", str(exc)


def get_current_commit() -> str:
    ok, out, _ = run_cmd("git rev-parse HEAD")
    return out if ok else "unknown"


def check_remote_updates() -> tuple[bool, str]:
    """Verifica si existen nuevos commits en origin/main."""
    run_cmd("git fetch origin main")
    ok, out, err = run_cmd("git rev-parse HEAD..origin/main")
    if not ok:
        logger.warning(f"No se pudo consultar la rama remota origin/main: {err}")
        return False, ""
    new_commits = [c for c in out.splitlines() if c.strip()]
    if new_commits:
        latest_remote = new_commits[0]
        logger.info(f"Nuevos commits detectados ({len(new_commits)} commits). Último remoto: {latest_remote[:8]}")
        return True, latest_remote
    return False, ""


def notify_cloud_status(version: str, status: str, rollback_to: str = None, message: str = ""):
    """Informa el resultado de la actualización al panel de la Nube."""
    if not CLOUD_URL or not GATEWAY_TOKEN:
        logger.debug("Omitiendo notificación a la nube: HIPOCRAFY_CLOUD_URL o GATEWAY_API_TOKEN no configurado.")
        return

    try:
        base = CLOUD_URL
        if base.endswith("/api"):
            base = base[:-4]
        endpoint = f"{base.rstrip('/')}/api/edge-gateway/software-status"

        payload = {
            "version": version[:8] if version else "unknown",
            "full_commit": version,
            "status": status,
            "rollback_to": rollback_to[:8] if rollback_to else None,
            "message": message,
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        headers = {
            "Authorization": f"Bearer {GATEWAY_TOKEN}",
            "X-Gateway-Token": GATEWAY_TOKEN,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=TIMEOUT)
        if resp.status_code == 200:
            logger.info(f"Estado de software notificado exitosamente a la nube ({status}).")
        else:
            logger.warning(f"Respuesta inesperada al notificar software-status: HTTP {resp.status_code}")
    except Exception as exc:
        logger.warning(f"Error notificando estado de software a la nube: {exc}")


def check_health(max_retries: int = 8, delay: int = 5) -> bool:
    """Realiza peticiones al endpoint /health local."""
    logger.info(f"Iniciando verificación de salud en {HEALTH_URL}...")
    time.sleep(3)
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(HEALTH_URL, timeout=4)
            if resp.status_code == 200:
                logger.info(f"Health check exitoso en intento {attempt}/{max_retries}.")
                return True
            else:
                logger.warning(f"Health check intento {attempt}/{max_retries}: HTTP {resp.status_code}")
        except Exception as exc:
            logger.warning(f"Health check intento {attempt}/{max_retries} falló: {exc}")
        time.sleep(delay)
    return False


def perform_update() -> bool:
    previous_commit = get_current_commit()
    logger.info(f"Commit actual antes de actualizar: {previous_commit[:8]}")

    # 1. Pull de código
    ok, out, err = run_cmd("git pull origin main")
    if not ok:
        logger.error(f"Fallo en git pull origin main: {err}")
        notify_cloud_status(previous_commit, "FAILED_PULL", message=err)
        return False

    new_commit = get_current_commit()
    logger.info(f"Código actualizado a commit: {new_commit[:8]}")

    # 2. Actualizar dependencias de Python si existe venv
    venv_pip = os.path.join(EDGE_DIR, "venv", "bin", "pip")
    req_file = os.path.join(EDGE_DIR, "requirements.txt")
    if os.path.exists(venv_pip) and os.path.exists(req_file):
        logger.info("Actualizando dependencias de Python (requirements.txt)...")
        run_cmd(f"{venv_pip} install -r {req_file} --quiet")

    # 3. Reiniciar servicio local systemd
    logger.info("Reiniciando servicio systemd hipocrafy-edge...")
    ok_restart, _, err_restart = run_cmd("sudo systemctl restart hipocrafy-edge")
    if not ok_restart:
        logger.error(f"Error al reiniciar servicio hipocrafy-edge: {err_restart}")

    # 4. Verificar salud del servicio
    if check_health():
        logger.info(f"✅ Actualización OTA a v{new_commit[:8]} completada exitosamente.")
        notify_cloud_status(new_commit, "SUCCESS", message="Actualización exitosa y servicio saludable.")
        return True

    # 5. ROLLBACK AUTOMÁTICO
    logger.critical(f"🚨 El servicio no respondió saludablemente tras la actualización. Iniciando ROLLBACK a {previous_commit[:8]}...")
    run_cmd(f"git reset --hard {previous_commit}")

    logger.info("Reiniciando servicio con la versión anterior estable...")
    run_cmd("sudo systemctl restart hipocrafy-edge")

    rollback_ok = check_health(max_retries=5, delay=4)
    if rollback_ok:
        logger.info(f"🛡️ Rollback exitoso. Nodo restaurado a versión estable {previous_commit[:8]}.")
        notify_cloud_status(new_commit, "FAILED_ROLLBACK", rollback_to=previous_commit, message="Health check falló. Se restauró versión previa.")
    else:
        logger.critical(f"❌ ALERTA CRÍTICA: El servicio no respondió incluso tras el rollback.")
        notify_cloud_status(new_commit, "CRITICAL_FAILURE", rollback_to=previous_commit, message="Fallo crítico: El servicio no responde post-rollback.")

    return False


def main():
    logger.info("=== Chequeo de Actualizaciones de Software OTA ===")
    has_updates, latest_commit = check_remote_updates()
    if has_updates:
        perform_update()
    else:
        current = get_current_commit()
        logger.info(f"El nodo Edge está al día (Commit: {current[:8]}).")


if __name__ == "__main__":
    main()
