"""
Simulador de Electrocardiógrafo (ECG 12 Derivaciones) — Hipocrafy Edge
Emite señales 1D de trazado electrocardiográfico (Ritmo Sinusal, AFib, Elevación ST).
"""

import sys
import os
import httpx
import argparse

def simulate_ecg(patient_dni: str, scenario: str, url: str):
    print(f"\n==================================================")
    print(f"🚀 SIMULANDO INGESTA DE ELECTROCARDIOGRAMA (ECG 12-LEAD)")
    print(f"==================================================")
    print(f"👤 Paciente DNI: {patient_dni}")
    print(f"🎭 Escenario:    {scenario.upper()}")
    print(f"🌐 Endpoint:     {url}")
    print(f"==================================================\n")

    if scenario == "sinusal":
        payload = {
            "patient_dni": patient_dni,
            "sample_rate_hz": 500,
            "heart_rate": 72,
            "pr_interval_ms": 150,
            "qrs_duration_ms": 86,
            "qtc_interval_ms": 410,
            "axis_degrees": 45,
            "st_elevation_leads": [],
            "is_afib": False
        }
    elif scenario == "stemi":
        payload = {
            "patient_dni": patient_dni,
            "sample_rate_hz": 500,
            "heart_rate": 105,
            "pr_interval_ms": 160,
            "qrs_duration_ms": 94,
            "qtc_interval_ms": 445,
            "axis_degrees": 60,
            "st_elevation_leads": ["V1", "V2", "V3", "V4"],
            "is_afib": False
        }
    elif scenario == "afib":
        payload = {
            "patient_dni": patient_dni,
            "sample_rate_hz": 500,
            "heart_rate": 128,
            "pr_interval_ms": 0,
            "qrs_duration_ms": 90,
            "qtc_interval_ms": 420,
            "axis_degrees": 30,
            "st_elevation_leads": [],
            "is_afib": True
        }
    else:
        payload = {
            "patient_dni": patient_dni,
            "sample_rate_hz": 500,
            "heart_rate": 75,
            "is_afib": False
        }

    try:
        response = httpx.post(url, json=payload, timeout=10.0)
        print(f"Status Code: {response.status_code}")
        print("Respuesta del Server:")
        print(response.json())
    except Exception as e:
        print(f"❌ Error enviando simulacion ECG: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulador de Electrocardiógrafo ECG")
    parser.add_argument("--dni", default="30456789", help="DNI del paciente")
    parser.add_argument("--scenario", default="sinusal", choices=["sinusal", "stemi", "afib"], help="Escenario clínico ECG")
    parser.add_argument("--url", default="http://localhost:8080/api/ecg/process", help="Endpoint API Edge")
    args = parser.parse_args()

    simulate_ecg(args.dni, args.scenario, args.url)
