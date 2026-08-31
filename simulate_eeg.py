"""
Simulador de Electroencefalógrafo (EEG Multicanal / EDF+) — Hipocrafy Edge
Emite datos de señales cerebrales (Normal, Crisis Ictal Epileptiforme, Encefalopatía).
"""

import sys
import os
import json
import urllib.request
import argparse

def simulate_eeg(patient_dni: str, scenario: str, url: str):
    print(f"\n==================================================")
    print(f"🚀 SIMULANDO INGESTA DE ELECTROENCEFALOGRAMA (EEG MULTICANAL)")
    print(f"==================================================")
    print(f"👤 Paciente DNI: {patient_dni}")
    print(f"🎭 Escenario:    {scenario.upper()}")
    print(f"🌐 Endpoint:     {url}")
    print(f"==================================================\n")

    if scenario == "normal":
        payload = {
            "patient_dni": patient_dni,
            "channels": ["F3-C3", "F4-C4", "C3-P3", "C4-P4", "P3-O1", "P4-O2"],
            "frequency_bands": {
                "delta_0_4hz": 12.5,
                "theta_4_8hz": 18.0,
                "alpha_8_12hz": 58.5,
                "beta_12_30hz": 11.0
            },
            "spikes_detected": 0,
            "is_seizure": False
        }
    elif scenario == "seizure":
        payload = {
            "patient_dni": patient_dni,
            "channels": ["F3-C3", "F4-C4", "C3-P3", "C4-P4", "P3-O1", "P4-O2"],
            "frequency_bands": {
                "delta_0_4hz": 42.0,
                "theta_4_8hz": 35.0,
                "alpha_8_12hz": 10.0,
                "beta_12_30hz": 13.0
            },
            "spikes_detected": 14,
            "is_seizure": True
        }
    else:
        payload = {
            "patient_dni": patient_dni,
            "channels": ["F3-C3", "F4-C4", "C3-P3", "C4-P4", "P3-O1", "P4-O2"],
            "frequency_bands": {
                "delta_0_4hz": 65.0,
                "theta_4_8hz": 25.0,
                "alpha_8_12hz": 5.0,
                "beta_12_30hz": 5.0
            },
            "spikes_detected": 2,
            "is_seizure": False
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
        print(f"❌ Error enviando simulacion EEG: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulador de Electroencefalógrafo EEG")
    parser.add_argument("--dni", default="30456789", help="DNI del paciente")
    parser.add_argument("--scenario", default="normal", choices=["normal", "seizure", "encefalopatia"], help="Escenario clínico EEG")
    parser.add_argument("--url", default="http://localhost:8080/api/eeg/process", help="Endpoint API Edge")
    args = parser.parse_args()

    simulate_eeg(args.dni, args.scenario, args.url)
