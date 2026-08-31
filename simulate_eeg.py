"""
Simulador de Electroencefalógrafo (EEG Multicanal / EDF+) — Hipocrafy Edge
Emite datos de señales cerebrales (Normal, Crisis Ictal Epileptiforme, Encefalopatía).
"""

import sys
import os
import httpx
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
                "alpha_8_13hz": 58.0,
                "beta_13_30hz": 11.5
            },
            "seizure_detected": False,
            "spike_wave_discharges": False
        }
    elif scenario == "seizure":
        payload = {
            "patient_dni": patient_dni,
            "channels": ["F3-C3", "F4-C4", "C3-P3", "C4-P4", "P3-O1", "P4-O2"],
            "frequency_bands": {
                "delta_0_4hz": 30.0,
                "theta_4_8hz": 40.0,
                "alpha_8_13hz": 15.0,
                "beta_13_30hz": 15.0
            },
            "seizure_detected": True,
            "spike_wave_discharges": True
        }
    elif scenario == "encefalopatia":
        payload = {
            "patient_dni": patient_dni,
            "channels": ["F3-C3", "F4-C4", "C3-P3", "C4-P4", "P3-O1", "P4-O2"],
            "frequency_bands": {
                "delta_0_4hz": 65.0,
                "theta_4_8hz": 22.0,
                "alpha_8_13hz": 8.0,
                "beta_13_30hz": 5.0
            },
            "seizure_detected": False,
            "spike_wave_discharges": False
        }
    else:
        payload = {
            "patient_dni": patient_dni,
            "channels": ["F3-C3", "F4-C4"],
            "seizure_detected": False
        }

    try:
        response = httpx.post(url, json=payload, timeout=10.0)
        print(f"Status Code: {response.status_code}")
        print("Respuesta del Server:")
        print(response.json())
    except Exception as e:
        print(f"❌ Error enviando simulacion EEG: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulador de Electroencefalógrafo EEG")
    parser.add_argument("--dni", default="30456789", help="DNI del paciente")
    parser.add_argument("--scenario", default="normal", choices=["normal", "seizure", "encefalopatia"], help="Escenario clínico EEG")
    parser.add_argument("--url", default="http://localhost:8080/api/eeg/process", help="Endpoint API Edge")
    args = parser.parse_args()

    simulate_eeg(args.dni, args.scenario, args.url)
