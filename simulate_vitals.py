"""
Simulador de Equipo de Signos Vitales y Balanza Antropométrica — Hipocrafy Edge
Permite simular la captura de signos vitales (normotenso, shock, crisis) y antropometría.
"""

import sys
import os
import json
import urllib.request
import argparse

def simulate_vitals(patient_dni: str, scenario: str, url: str):
    print(f"\n==================================================")
    print(f"🚀 SIMULANDO INGESTA DE SIGNOS VITALES & ANTROPOMETRÍA")
    print(f"==================================================")
    print(f"👤 Paciente DNI: {patient_dni}")
    print(f"🎭 Escenario:    {scenario.upper()}")
    print(f"🌐 Endpoint:     {url}")
    print(f"==================================================\n")

    if scenario == "normotenso":
        payload = {
            "patient_dni": patient_dni,
            "heart_rate": 72,
            "sbp": 120,
            "dbp": 80,
            "spo2": 98,
            "temp_c": 36.6,
            "resp_rate": 14,
            "height_cm": 175,
            "weight_kg": 74
        }
    elif scenario == "shock":
        payload = {
            "patient_dni": patient_dni,
            "heart_rate": 135,
            "sbp": 85,
            "dbp": 50,
            "spo2": 89,
            "temp_c": 38.8,
            "resp_rate": 28,
            "height_cm": 170,
            "weight_kg": 65
        }
    elif scenario == "obesidad_metabolico":
        payload = {
            "patient_dni": patient_dni,
            "heart_rate": 88,
            "sbp": 145,
            "dbp": 95,
            "spo2": 95,
            "temp_c": 36.8,
            "resp_rate": 18,
            "height_cm": 172,
            "weight_kg": 108
        }
    else:
        payload = {
            "patient_dni": patient_dni,
            "heart_rate": 92,
            "sbp": 130,
            "dbp": 85,
            "spo2": 96,
            "temp_c": 37.0,
            "resp_rate": 16,
            "height_cm": 168,
            "weight_kg": 70
        }

    try:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=10.0) as response:
            res_body = json.loads(response.read().decode('utf-8'))
            print(f"Status Code: {response.status}")
            print("Respuesta del Server:")
            print(res_body)
    except Exception as e:
        print(f"❌ Error enviando simulacion: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulador de Signos Vitales y Balanza Antropométrica")
    parser.add_argument("--dni", default="30456789", help="DNI del paciente")
    parser.add_argument("--scenario", default="normotenso", choices=["normotenso", "shock", "obesidad_metabolico"], help="Escenario clínico")
    parser.add_argument("--url", default="http://localhost:8080/api/vitals/ingest", help="Endpoint API Edge")
    args = parser.parse_args()

    simulate_vitals(args.dni, args.scenario, args.url)
