#!/usr/bin/env python3
"""
Reset completo del pipeline de test en el Jetson y carga de DICOMs reales.

Pasos:
  1. Limpia todos los estudios de Orthanc (Jetson)
  2. Limpia la tabla local_studies del SQLite (via SSH)
  3. Descarga 10 estudios DICOM reales y los sube al Jetson

Uso:
    python scripts/reset_and_load.py <JETSON_IP>

Ejemplo:
    python scripts/reset_and_load.py 192.168.1.50
"""

import subprocess
import sys
import time

import requests

# ─── Config ───────────────────────────────────────────────────────────────────

if len(sys.argv) < 2:
    print("Uso: python scripts/reset_and_load.py <JETSON_IP>")
    sys.exit(1)

JETSON_IP      = sys.argv[1]
JETSON_USER    = "pmoraga"
SQLITE_DB      = "/home/pmoraga/hipocrafy-edge/edge_data.db"

ORTHANC_URL    = f"http://{JETSON_IP}:8042"
ORTHANC_AUTH   = ("orthanc", "orthanc")

SOURCE_URL     = "https://orthanc.uclouvain.be/demo"
SOURCE_AUTH    = ("orthanc", "orthanc")

MAX_STUDIES        = 10
MAX_SERIES_PER_STU = 2
MAX_INST_PER_SER   = 5

# ─── Helpers ──────────────────────────────────────────────────────────────────

def header(title: str):
    print(f"\n{'─' * 62}")
    print(f"  {title}")
    print(f"{'─' * 62}")


def check_reachable(url: str, auth: tuple, label: str) -> bool:
    try:
        r = requests.get(f"{url}/system", auth=auth, timeout=8)
        if r.status_code == 200:
            v = r.json().get("Version", "?")
            print(f"  ✓ {label} — Orthanc {v}")
            return True
        print(f"  ✗ {label} — HTTP {r.status_code}")
        return False
    except Exception as e:
        print(f"  ✗ {label} — {e}")
        return False


# ─── Paso 1: Limpiar Orthanc ──────────────────────────────────────────────────

def clear_orthanc():
    header("Paso 1 — Limpiando Orthanc (Jetson)")
    try:
        resp = requests.get(f"{ORTHANC_URL}/studies", auth=ORTHANC_AUTH, timeout=10)
        resp.raise_for_status()
        study_ids = resp.json()
    except Exception as e:
        print(f"  ERROR al listar estudios: {e}")
        return

    if not study_ids:
        print("  Sin estudios que borrar.")
        return

    print(f"  Borrando {len(study_ids)} estudios...")
    for sid in study_ids:
        try:
            requests.delete(f"{ORTHANC_URL}/studies/{sid}", auth=ORTHANC_AUTH, timeout=10)
        except Exception:
            pass

    # Verificar
    remaining = requests.get(f"{ORTHANC_URL}/studies", auth=ORTHANC_AUTH, timeout=10).json()
    print(f"  ✓ Orthanc limpio — {len(remaining)} estudios restantes")


# ─── Paso 2: Limpiar SQLite via SSH ───────────────────────────────────────────

def clear_sqlite():
    header("Paso 2 — Limpiando SQLite en Jetson (via SSH)")
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        f"{JETSON_USER}@{JETSON_IP}",
        f'sqlite3 {SQLITE_DB} "DELETE FROM local_studies;"'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("  ✓ local_studies vaciada")
    else:
        print(f"  WARN: {result.stderr.strip() or 'sin error (puede que sqlite3 no esté instalado)'}")
        print("  → Continuando igual; el edge creará registros nuevos al procesar.")


# ─── Paso 3: Cargar DICOMs reales ─────────────────────────────────────────────

def source_get(path: str) -> requests.Response:
    return requests.get(f"{SOURCE_URL}{path}", auth=SOURCE_AUTH, timeout=30)


def load_studies():
    header("Paso 3 — Cargando DICOMs reales desde Orthanc demo")

    print(f"\n  Fuente : {SOURCE_URL}")
    print(f"  Destino: {ORTHANC_URL}")

    try:
        all_ids = source_get("/studies").json()
    except Exception as e:
        print(f"  ERROR al obtener lista de estudios: {e}")
        sys.exit(1)

    selected = all_ids[:MAX_STUDIES]
    print(f"\n  Seleccionados {len(selected)} de {len(all_ids)} estudios disponibles\n")

    uploaded  = 0
    study_ok  = 0

    for i, study_id in enumerate(selected):
        print(f"  [{i+1:2}/{len(selected)}] {study_id[:8]}...", end="", flush=True)

        try:
            series_ids = source_get(f"/studies/{study_id}").json().get("Series", [])
        except Exception as e:
            print(f" ERROR: {e}")
            continue

        inst_count = 0
        for series_id in series_ids[:MAX_SERIES_PER_STU]:
            try:
                inst_ids = source_get(f"/series/{series_id}").json().get("Instances", [])
            except Exception:
                continue

            for inst_id in inst_ids[:MAX_INST_PER_SER]:
                try:
                    data = source_get(f"/instances/{inst_id}/file").content
                except Exception:
                    continue

                resp = requests.post(
                    f"{ORTHANC_URL}/instances",
                    auth=ORTHANC_AUTH,
                    data=data,
                    headers={"Content-Type": "application/dicom"},
                    timeout=30,
                )
                if resp.status_code in (200, 201):
                    uploaded   += 1
                    inst_count += 1

        if inst_count:
            study_ok += 1
            print(f" {inst_count} instancias OK")
        else:
            print(" sin instancias")

        time.sleep(0.3)

    return uploaded, study_ok, len(selected)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("  Hipocrafy — Reset + Test Pipeline")
    print(f"  Jetson: {JETSON_IP}")
    print("=" * 62)

    print("\nVerificando conectividad...")
    if not check_reachable(ORTHANC_URL, ORTHANC_AUTH, f"Orthanc Jetson ({JETSON_IP}:8042)"):
        print(f"\nERROR: No se puede conectar a {ORTHANC_URL}")
        sys.exit(1)
    if not check_reachable(SOURCE_URL, SOURCE_AUTH, "Orthanc demo (fuente)"):
        print("\nERROR: No se puede conectar al servidor demo.")
        sys.exit(1)

    clear_orthanc()
    clear_sqlite()
    uploaded, study_ok, total = load_studies()

    print("\n" + "=" * 62)
    print("  RESUMEN")
    print("=" * 62)
    print(f"  Estudios cargados : {study_ok}/{total}")
    print(f"  Instancias totales: {uploaded}")
    print()
    print("  Verificá el pipeline en:")
    print(f"    Edge UI   → http://{JETSON_IP}:8080")
    print(f"    Orthanc   → http://{JETSON_IP}:8042/app")
    print( "    Etiquetado→ frontend /medico/etiquetado")
    print("=" * 62)
    print()


if __name__ == "__main__":
    main()
