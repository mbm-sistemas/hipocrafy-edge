#!/usr/bin/env python3
"""
Descarga estudios DICOM reales desde el servidor demo público de Orthanc
y los sube al Jetson (edge01.local:8042) para testear el pipeline completo.

Uso:
    pip install requests
    python scripts/load_test_studies.py

Flujo: Orthanc edge → webhook → análisis IA → backend → etiquetado médico
"""

import sys
import time

import requests

# ─── Configuración ────────────────────────────────────────────────────────────
SOURCE_URL   = "https://orthanc.uclouvain.be/demo"
SOURCE_AUTH  = ("orthanc", "orthanc")

_jetson_host = sys.argv[1] if len(sys.argv) > 1 else "edge01.local"
ORTHANC_URL  = f"http://{_jetson_host}:8042"
ORTHANC_AUTH = ("orthanc", "orthanc")

MAX_STUDIES      = 10
MAX_INST_PER_SER = 5   # instancias por serie (suficiente para el pipeline)


# ─── Source: Orthanc demo ─────────────────────────────────────────────────────

def source_get(path: str) -> requests.Response:
    return requests.get(f"{SOURCE_URL}{path}", auth=SOURCE_AUTH, timeout=30)


def get_studies() -> list[str]:
    resp = source_get("/studies")
    resp.raise_for_status()
    return resp.json()


def get_study_series(study_id: str) -> list[str]:
    resp = source_get(f"/studies/{study_id}")
    resp.raise_for_status()
    return resp.json().get("Series", [])


def get_series_instances(series_id: str) -> list[str]:
    resp = source_get(f"/series/{series_id}")
    resp.raise_for_status()
    return resp.json().get("Instances", [])


def download_instance(instance_id: str) -> bytes | None:
    resp = source_get(f"/instances/{instance_id}/file")
    if resp.status_code == 200:
        return resp.content
    return None


# ─── Destino: Orthanc Jetson ──────────────────────────────────────────────────

def orthanc_upload(dicom_bytes: bytes) -> tuple[int, str]:
    resp = requests.post(
        f"{ORTHANC_URL}/instances",
        auth=ORTHANC_AUTH,
        data=dicom_bytes,
        headers={"Content-Type": "application/dicom"},
        timeout=30,
    )
    try:
        status = resp.json().get("Status", "?")
    except Exception:
        status = "?"
    return resp.status_code, status


def orthanc_stats(url: str, auth: tuple) -> dict:
    try:
        return requests.get(f"{url}/statistics", auth=auth, timeout=10).json()
    except Exception:
        return {}


def check_reachable(url: str, auth: tuple, label: str) -> bool:
    try:
        r = requests.get(f"{url}/system", auth=auth, timeout=8)
        if r.status_code == 200:
            info = r.json()
            print(f"  {label}: OK — Orthanc {info.get('Version','?')}")
            return True
        print(f"  {label}: HTTP {r.status_code}")
        return False
    except Exception as e:
        print(f"  {label}: no alcanzable — {e}")
        return False


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("  Hipocrafy — Test pipeline con DICOMs reales")
    print(f"  Fuente  : {SOURCE_URL}")
    print(f"  Destino : {ORTHANC_URL}")
    print("=" * 62)

    print("\nVerificando conectividad...")
    if not check_reachable(SOURCE_URL, SOURCE_AUTH, "Orthanc demo (fuente)"):
        print("\nERROR: No se puede conectar al servidor fuente.")
        sys.exit(1)
    if not check_reachable(ORTHANC_URL, ORTHANC_AUTH, "Orthanc Jetson (destino)"):
        print(f"\nERROR: No se puede conectar a {ORTHANC_URL}")
        print("Verificá que el Jetson esté en la red y el servicio corriendo.")
        sys.exit(1)

    before = orthanc_stats(ORTHANC_URL, ORTHANC_AUTH)
    print(f"\nEstudios actuales en Jetson: {before.get('CountStudies', 0)}")

    # Obtener lista de estudios del servidor demo
    print(f"\nObteniendo estudios desde servidor demo...")
    try:
        all_study_ids = get_studies()
    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    selected = all_study_ids[:MAX_STUDIES]
    print(f"Seleccionados {len(selected)} estudios de {len(all_study_ids)} disponibles\n")

    uploaded   = 0
    study_ok   = 0

    for i, study_id in enumerate(selected):
        print(f"[{i+1:2}/{len(selected)}] Estudio {study_id[:8]}...")

        try:
            series_ids = get_study_series(study_id)
        except Exception as e:
            print(f"         ERROR obteniendo series: {e}")
            continue

        inst_uploaded = 0
        for series_id in series_ids[:2]:  # máximo 2 series por estudio
            try:
                instance_ids = get_series_instances(series_id)
            except Exception:
                continue

            for inst_id in instance_ids[:MAX_INST_PER_SER]:
                dicom = download_instance(inst_id)
                if not dicom:
                    continue
                http_code, status = orthanc_upload(dicom)
                if http_code in (200, 201):
                    uploaded += 1
                    inst_uploaded += 1
                else:
                    print(f"         WARN: HTTP {http_code} — {status}")

        if inst_uploaded > 0:
            study_ok += 1
            print(f"         {inst_uploaded} instancias subidas OK")
        else:
            print("         Sin instancias subidas")

        time.sleep(0.3)

    # Resumen
    after = orthanc_stats(ORTHANC_URL, ORTHANC_AUTH)
    print("\n" + "=" * 62)
    print(f"  Estudios procesados : {study_ok}/{len(selected)}")
    print(f"  Instancias subidas  : {uploaded}")
    print(f"  Estudios en Jetson  : {after.get('CountStudies','?')} (antes: {before.get('CountStudies',0)})")
    print(f"  Pacientes en Jetson : {after.get('CountPatients','?')}")
    print("=" * 62)
    print()
    print("Verificá el pipeline:")
    print("  Cola técnico  →  http://edge01.local:8080")
    print("  Orthanc PACS  →  http://edge01.local:8042/app")
    print("  Etiquetado    →  frontend /medico/etiquetado")
    print()


if __name__ == "__main__":
    main()
