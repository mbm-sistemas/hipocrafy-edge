"""
╔══════════════════════════════════════════════════════════════╗
║  HIPOCRAFY EDGE - Simulación de Ecógrafo Virtual           ║
║  Este script simula el flujo completo:                      ║
║  Ecógrafo → PACS → Gateway IA → Dashboard Técnico          ║
╚══════════════════════════════════════════════════════════════╝

Uso:
    python demo_simulation.py

Sin Docker, sin Orthanc. Simula todo localmente.
"""
import httpx
import json
import time
import random
import sqlite3
import os
import sys
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

GATEWAY_URL = "http://localhost:8080"
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edge_data.db")

# ═══════════════════════════════════════════════════════════
#  PACIENTES FICTICIOS (simulan datos DICOM reales)
# ═══════════════════════════════════════════════════════════
FAKE_PATIENTS = [
    {"dni": "30456789", "name": "María García",    "modality": "US",  "body_part": "Abdomen"},
    {"dni": "28123456", "name": "Carlos Rodríguez","modality": "CT",  "body_part": "Tórax"},
    {"dni": "35789012", "name": "Ana Martínez",    "modality": "MR",  "body_part": "Columna Lumbar"},
    {"dni": "40234567", "name": "Juan López",      "modality": "US",  "body_part": "Tiroides"},
    {"dni": "33567890", "name": "Lucía Fernández", "modality": "CR",  "body_part": "Rodilla Derecha"},
]

# Hallazgos IA posibles (simulados)
FINDINGS = [
    {"finding": "Normal",              "confidence": 0.96, "anomalies": []},
    {"finding": "Normal",              "confidence": 0.98, "anomalies": []},
    {"finding": "Hallazgo sospechoso", "confidence": 0.82, "anomalies": [
        {"label": "Nódulo calcificado", "confidence": 0.78, "location": "Lóbulo inferior derecho"}
    ]},
    {"finding": "Normal",              "confidence": 0.91, "anomalies": []},
    {"finding": "Anomalía detectada",  "confidence": 0.87, "anomalies": [
        {"label": "Quiste simple",      "confidence": 0.85, "location": "Polo superior riñón izquierdo"},
        {"label": "Litiasis renal",     "confidence": 0.72, "location": "Cáliz inferior riñón derecho"}
    ]},
]


def print_header():
    print()
    print("=" * 60)
    print("   🏥 HIPOCRAFY EDGE - Simulador de Ecógrafo Virtual")
    print("=" * 60)
    print()


def simulate_dicom_send(patient, finding):
    """Simula el envío de una imagen DICOM al Gateway."""
    study_uid = f"1.2.840.113619.{random.randint(100000, 999999)}.{int(time.time())}"

    print(f"  📡 Enviando estudio DICOM...")
    print(f"     Paciente:  {patient['name']} (DNI: {patient['dni']})")
    print(f"     Modalidad: {patient['modality']} - {patient['body_part']}")
    print(f"     Study UID: {study_uid}")

    # Insertar directamente en la base de datos local (simula el proceso completo)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT OR REPLACE INTO local_studies 
               (study_instance_uid, patient_dni, modality, ai_findings, sync_status, created_at) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                study_uid,
                patient['dni'],
                patient['modality'],
                json.dumps(finding),
                random.choice(['pending', 'synced', 'pending']),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
        )

    return study_uid


def check_gateway_health():
    """Verifica que el Gateway esté corriendo."""
    try:
        r = httpx.get(f"{GATEWAY_URL}/health", timeout=5.0)
        if r.status_code == 200:
            data = r.json()
            print(f"  ✅ Gateway ONLINE")
            print(f"     Nombre: {data.get('gateway_name', 'N/A')}")
            print(f"     Cloud:  {data.get('cloud_status', 'N/A')}")
            print(f"     Estudios locales: {data.get('local_studies_count', 0)}")
            return True
        else:
            print(f"  ⚠️  Gateway respondió con status {r.status_code}")
            return True
    except Exception as e:
        print(f"  ❌ Gateway no responde: {e}")
        print(f"     ¿Está corriendo en {GATEWAY_URL}?")
        print(f"     Ejecutá: .\\venv\\Scripts\\uvicorn.exe main:app --reload --port 8080")
        return False


def run_full_simulation():
    """Ejecuta la simulación completa."""
    print_header()

    # 1. Verificar Gateway
    print("─" * 50)
    print("  PASO 1: Verificando Gateway...")
    print("─" * 50)
    gateway_ok = check_gateway_health()
    print()

    # 2. Simular envío de estudios
    print("─" * 50)
    print("  PASO 2: Simulando envío desde ecógrafo virtual...")
    print("─" * 50)
    print()

    uids = []
    for i, (patient, finding) in enumerate(zip(FAKE_PATIENTS, FINDINGS)):
        print(f"  📋 Estudio {i+1}/{len(FAKE_PATIENTS)}:")
        uid = simulate_dicom_send(patient, finding)
        uids.append(uid)

        # Resultado IA
        emoji = "✅" if finding['finding'] == "Normal" else "⚠️"
        print(f"     Resultado IA: {emoji} {finding['finding']} ({finding['confidence']*100:.0f}% confianza)")
        if finding['anomalies']:
            for a in finding['anomalies']:
                print(f"       → {a['label']} en {a['location']} ({a['confidence']*100:.0f}%)")
        print()
        time.sleep(0.5)  # Pausa dramática 😄

    # 3. Verificar base de datos local
    print("─" * 50)
    print("  PASO 3: Verificando base de datos local...")
    print("─" * 50)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        studies = conn.execute("SELECT * FROM local_studies ORDER BY created_at DESC LIMIT 10").fetchall()
        print(f"  📊 Total de estudios en la base local: {len(studies)}")
        print()
        for s in studies:
            findings_data = json.loads(s['ai_findings'])
            status_icon = "🟢" if s['sync_status'] == 'synced' else "🟡"
            finding_icon = "✅" if findings_data.get('finding') == 'Normal' else "⚠️"
            print(f"     {status_icon} DNI: {s['patient_dni']} | {s['modality']} | {finding_icon} {findings_data.get('finding', 'N/A')} | {s['created_at']}")

    # 4. Resumen
    print()
    print("=" * 60)
    print("  🎉 SIMULACIÓN COMPLETA")
    print("=" * 60)
    print()
    print(f"  ✅ {len(uids)} estudios procesados por la IA")
    normals = sum(1 for f in FINDINGS if f['finding'] == 'Normal')
    alerts = len(FINDINGS) - normals
    print(f"  ✅ {normals} normales, {alerts} con hallazgos")
    print()
    if gateway_ok:
        print(f"  🖥️  Abrí el Dashboard del Técnico: {GATEWAY_URL}")
        print(f"     → Ahí vas a ver todos los estudios procesados")
        print(f"     → Click en 'Ver Informe' para el reporte de IA imprimible")
    print()
    print(f"  👨‍⚕️ El Médico ve estos estudios en:")
    print(f"     → Web: https://qas.hypocrafy.mbmsistemas.com.ar (login como médico)")
    print(f"     → Mobile: App Hipocrafy → Home del Médico → 'Estudios IA Pendientes'")
    print()
    print("  📝 Nota: Los estudios con status 🟡 PENDIENTE se sincronizarán")
    print("     automáticamente cuando se configure el token de Gateway.")
    print()


if __name__ == "__main__":
    run_full_simulation()
