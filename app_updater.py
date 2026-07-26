"""
OTA App Updater — Hipocrafy Edge

Chequea periódicamente si se publicó una versión nueva del CÓDIGO del edge
(no del modelo ONNX, eso lo maneja model_updater.py) y, si AUTO_INSTALL_APP_UPDATES
está en "true", la descarga e instala sola. Mismo patrón que model_updater.py:
poll -> comparar version local -> descargar -> instalar -> reportar.

Por diseño arranca INACTIVO (solo detecta y reporta, no instala) hasta que se
confirme manualmente en el equipo real que la instalación funciona. Ver README
en scripts/publish_release.sh para el flujo de publicación.
"""

import logging
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("HipocrafyAppOTA")

CLOUD_URL = os.getenv("HIPOCRAFY_CLOUD_URL", "").rstrip("/")
GATEWAY_TOKEN = os.getenv("GATEWAY_API_TOKEN", "")
APP_DIR = Path(os.getenv("APP_DIR", "/home/pmoraga/hipocrafy-edge"))
BACKUP_DIR = Path(os.getenv("APP_BACKUP_DIR", "/home/pmoraga/hipocrafy-edge-backups"))
VERSION_FILE = APP_DIR / "VERSION"
TIMEOUT = 30
HEALTH_URL = "http://localhost:8080/health"
HEALTH_RETRIES = 10
HEALTH_WAIT_SECONDS = 3

# El nombre real del servicio (ver hipocrafy-edge.service en la raíz del repo) es
# uno solo: "hipocrafy-edge". No asumir los nombres del workflow de CI viejo
# (hipocrafy-api/hipocrafy-dicom), que están desactualizados. Configurable por si
# algún equipo lo corre distinto.
APP_SERVICES = [s.strip() for s in os.getenv("APP_SYSTEMD_SERVICES", "hipocrafy-edge.service").split(",") if s.strip()]

# Apagado por defecto a propósito: hasta que se valide en el equipo real que
# la instalación automática funciona (permisos de sudo, servicios correctos),
# este loop solo detecta y reporta disponibilidad, nunca instala solo.
AUTO_INSTALL_APP_UPDATES = os.getenv("AUTO_INSTALL_APP_UPDATES", "false").lower() == "true"

# Rutas que nunca se deben pisar al instalar una release nueva (datos locales,
# entorno, y el propio venv que no viaja en el tarball de la release).
PRESERVE_PATHS = [
    ".env",
    "venv",
    "edge_data.db",
    "estudios_recibidos",
    "estudios_procesados",
    "models",  # modelos ONNX descargados por model_updater.py, no forman parte del código
]


def _gateway_headers() -> dict:
    return {"Authorization": f"Bearer {GATEWAY_TOKEN}", "Accept": "application/json"}


def _api_base() -> str:
    # HIPOCRAFY_CLOUD_URL normalmente ya viene con el path completo (ver el
    # default de main.py: ".../api/edge-gateway") — main.py lo usa tal cual
    # (f"{CLOUD_URL}/studies"). Antes esta función asumía que faltaba el sufijo
    # y lo volvía a agregar, duplicando el path si CLOUD_URL ya lo traía.
    base = CLOUD_URL.rstrip("/")
    if base.endswith("/edge-gateway"):
        return base
    if base.endswith("/api"):
        return base + "/edge-gateway"
    return base + "/api/edge-gateway"


def _report_status(version: str, status: str, error: str | None = None):
    """Best-effort: un fallo al reportar no debe interrumpir el flujo de update."""
    try:
        resp = requests.post(
            f"{_api_base()}/release-status",
            headers=_gateway_headers(),
            json={"version": version, "status": status, "error": error},
            timeout=TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning(f"No se pudo reportar release-status ({status}): HTTP {resp.status_code}")
    except Exception as exc:
        logger.warning(f"Error reportando release-status ({status}): {exc}")


def get_local_version() -> str:
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    return "unknown"


def _get_remote_latest() -> dict | None:
    try:
        resp = requests.get(f"{_api_base()}/releases/latest", headers=_gateway_headers(), timeout=TIMEOUT)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        logger.warning(f"No se pudo consultar releases/latest: {exc}")
        return None


def _download_tarball(url: str, dest: Path) -> bool:
    try:
        resp = requests.get(url, headers=_gateway_headers(), timeout=120, stream=True)
        if resp.status_code != 200:
            logger.error(f"Descarga de release falló: HTTP {resp.status_code}")
            return False
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                f.write(chunk)
        return True
    except Exception as exc:
        logger.error(f"Error descargando release: {exc}")
        return False


def _backup_current(version: str) -> Path | None:
    """Empaqueta el código actual (sin datos/entorno) antes de instalar, para poder revertir."""
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_path = BACKUP_DIR / f"{version}.tar.gz"
        with tarfile.open(backup_path, "w:gz") as tar:
            for item in APP_DIR.iterdir():
                if item.name in PRESERVE_PATHS or item.name == ".git":
                    continue
                tar.add(item, arcname=item.name)
        return backup_path
    except Exception as exc:
        logger.error(f"No se pudo generar backup antes de instalar: {exc}")
        return None


def _extract_over_app_dir(tarball: Path):
    """Extrae el tarball de la release sobre APP_DIR, sin tocar PRESERVE_PATHS."""
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(tarball, "r:gz") as tar:
            tar.extractall(tmp)
        tmp_path = Path(tmp)
        for item in tmp_path.iterdir():
            if item.name in PRESERVE_PATHS:
                continue
            dest = APP_DIR / item.name
            if dest.is_dir():
                shutil.rmtree(dest)
            elif dest.exists():
                dest.unlink()
            shutil.move(str(item), str(dest))


def _restart_services() -> bool:
    """Requiere sudoers configurado sin password para 'systemctl restart' de APP_SERVICES."""
    try:
        subprocess.run(
            ["sudo", "systemctl", "restart", *APP_SERVICES],
            check=True, timeout=30,
        )
        return True
    except Exception as exc:
        logger.error(f"No se pudieron reiniciar los servicios {APP_SERVICES}: {exc}")
        return False


def _wait_healthy() -> bool:
    for _ in range(HEALTH_RETRIES):
        time.sleep(HEALTH_WAIT_SECONDS)
        try:
            resp = requests.get(HEALTH_URL, timeout=5)
            if resp.status_code == 200:
                return True
        except Exception:
            continue
    return False


def _restore_backup(backup_path: Path):
    logger.error("Health check post-instalación falló — revirtiendo a la versión anterior.")
    _extract_over_app_dir(backup_path)
    _restart_services()


def check_and_update() -> bool:
    """
    Devuelve True si se detectó (y, si AUTO_INSTALL_APP_UPDATES, se instaló) una
    versión nueva. Retries no aplican acá (a diferencia de model_updater.py) porque
    un chequeo fallido simplemente se reintenta en el próximo ciclo de 6hs.
    """
    if not CLOUD_URL or not GATEWAY_TOKEN:
        logger.warning("App OTA skipped: HIPOCRAFY_CLOUD_URL o GATEWAY_API_TOKEN no configurados.")
        return False

    remote = _get_remote_latest()
    if not remote:
        return False

    local_version = get_local_version()
    remote_version = remote.get("version")

    if local_version == remote_version:
        logger.debug(f"App ya está en la última versión publicada (v{remote_version}).")
        return False

    logger.info(f"Nueva release de app disponible: v{remote_version} (local=v{local_version})")

    if not AUTO_INSTALL_APP_UPDATES:
        _report_status(remote_version, "idle", error=None)
        logger.info(
            "AUTO_INSTALL_APP_UPDATES=false — solo se detecta y reporta, no se instala sola. "
            "Activar manualmente en .env una vez validado en el equipo."
        )
        return True

    _report_status(remote_version, "downloading")
    with tempfile.TemporaryDirectory() as tmp:
        tarball = Path(tmp) / f"{remote_version}.tar.gz"
        if not _download_tarball(remote["download_url"], tarball):
            _report_status(remote_version, "failed", "Fallo al descargar el paquete.")
            return False

        backup_path = _backup_current(local_version)
        if backup_path is None:
            _report_status(remote_version, "failed", "Fallo al generar backup previo, se aborta por seguridad.")
            return False

        _report_status(remote_version, "installing")
        try:
            _extract_over_app_dir(tarball)
            VERSION_FILE.write_text(remote_version)
        except Exception as exc:
            logger.error(f"Fallo al extraer la release: {exc}")
            _restore_backup(backup_path)
            _report_status(local_version, "failed", f"Fallo al extraer release: {exc}")
            return False

        if not _restart_services():
            _restore_backup(backup_path)
            _report_status(local_version, "failed", "Fallo al reiniciar servicios tras instalar.")
            return False

        if not _wait_healthy():
            _restore_backup(backup_path)
            _report_status(local_version, "failed", "Health check post-instalación falló, se revirtió.")
            return False

    logger.info(f"App actualizada a v{remote_version} y healthy.")
    _report_status(remote_version, "success")
    return True


def run_app_ota_check() -> bool:
    try:
        return check_and_update()
    except Exception as exc:
        logger.error(f"Error inesperado en chequeo de app OTA: {exc}")
        return False
