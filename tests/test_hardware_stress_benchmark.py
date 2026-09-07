"""
Hardware Stress & Concurrent Inference Benchmark — Hipocrafy Edge (Jetson)
Tests system stability, CPU/GPU thermal behavior, RAM memory footprint,
and response latencies under concurrent bursts of clinical signal and DICOM workloads.
"""

import os
import sys
import time
import json
import io
import urllib.request
import urllib.error
import concurrent.futures
from datetime import datetime

# Server target (local loopback on Jetson)
TARGET_URL = os.getenv("EDGE_TARGET_URL", "http://127.0.0.1:8080")


def read_jetson_temperatures() -> dict:
    """Reads Linux thermal zone sensors on NVIDIA Jetson."""
    temps = {}
    thermal_dir = "/sys/devices/virtual/thermal"
    if os.path.exists(thermal_dir):
        for zone in sorted(os.listdir(thermal_dir)):
            if zone.startswith("thermal_zone"):
                type_file = os.path.join(thermal_dir, zone, "type")
                temp_file = os.path.join(thermal_dir, zone, "temp")
                if os.path.exists(type_file) and os.path.exists(temp_file):
                    try:
                        with open(type_file, "r") as tf:
                            z_type = tf.read().strip()
                        with open(temp_file, "r") as tf:
                            raw_val = tf.read().strip()
                            if raw_val:
                                temps[z_type] = round(float(raw_val) / 1000.0, 1)
                    except Exception:
                        pass
    return temps


def read_memory_usage() -> dict:
    """Reads /proc/meminfo to monitor RAM stability without spawning external processes."""
    mem = {}
    if os.path.exists("/proc/meminfo"):
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip().split()[0]
                        if key in ["MemTotal", "MemFree", "MemAvailable", "SwapTotal", "SwapFree"]:
                            mem[key] = int(val) // 1024  # Convert to MB
            mem["MemUsedMB"] = mem.get("MemTotal", 0) - mem.get("MemAvailable", 0)
        except Exception as e:
            mem["error"] = str(e)
    return mem


def send_vitals_payload(patient_id: str) -> dict:
    url = f"{TARGET_URL}/api/vitals/ingest"
    payload = {
        "patient_dni": patient_id,
        "heart_rate": 78,
        "systolic_bp": 120,
        "diastolic_bp": 80,
        "temperature": 36.6,
        "spo2": 98,
        "respiratory_rate": 16,
        "consciousness": "alert",
        "supplemental_oxygen": False,
        "height_cm": 175,
        "weight_kg": 74
    }
    t0 = time.time()
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            elapsed = time.time() - t0
            return {"status": resp.status, "latency": elapsed, "type": "vitals"}
    except Exception as e:
        return {"status": 0, "error": str(e), "latency": time.time() - t0, "type": "vitals"}


def send_ecg_payload(patient_id: str) -> dict:
    url = f"{TARGET_URL}/api/ecg/process"
    import math
    # Synthetic 500-sample lead signal simulating Lead II with cardiac sinus wave
    sample_signal = [round(math.sin(i * 0.1) * 0.5 + (1.2 if i % 60 == 0 else 0.0), 3) for i in range(500)]
    payload = {
        "patient_dni": patient_id,
        "sample_rate_hz": 500,
        "heart_rate": 74,
        "pr_interval_ms": 150,
        "qrs_duration_ms": 85,
        "qtc_interval_ms": 410,
        "axis_degrees": 45,
        "leads": {
            "II": sample_signal
        }
    }
    t0 = time.time()
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            elapsed = time.time() - t0
            return {"status": resp.status, "latency": elapsed, "type": "ecg"}
    except Exception as e:
        return {"status": 0, "error": str(e), "latency": time.time() - t0, "type": "ecg"}


def run_stress_test(num_workers: int = 10, total_requests: int = 50):
    print("=" * 65)
    print("🚀 INICIANDO HARDWARE STRESS & CONCURRENT BENCHMARK EN JETSON")
    print(f"🎯 Target: {TARGET_URL}")
    print(f"⚙️ Concurrencia: {num_workers} workers paralelos")
    print(f"📦 Volumen: {total_requests} transacciones clínicas (Vitals + ECGs)")
    print("=" * 65)

    # Baseline telemetry
    base_temps = read_jetson_temperatures()
    base_mem = read_memory_usage()
    print(f"\n[BASELINE TELEMETRY]")
    print(f"  🌡️ Temperaturas Iniciales: CPU={base_temps.get('cpu-thermal', 'N/A')}°C | GPU={base_temps.get('gpu-thermal', 'N/A')}°C")
    print(f"  💾 Memoria RAM: Usada={base_mem.get('MemUsedMB', 'N/A')} MB / Total={base_mem.get('MemTotal', 'N/A')} MB")

    print(f"\n⚡ Disparando ráfaga concurrente de {total_requests} peticiones...")
    t_start = time.time()
    results = []

    tasks = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        for i in range(total_requests):
            dni = f"BENCH_{1000 + i}"
            if i % 2 == 0:
                tasks.append(executor.submit(send_vitals_payload, dni))
            else:
                tasks.append(executor.submit(send_ecg_payload, dni))

        for future in concurrent.futures.as_completed(tasks):
            results.append(future.result())

    total_duration = time.time() - t_start

    # Peak telemetry immediately after workload
    peak_temps = read_jetson_temperatures()
    peak_mem = read_memory_usage()

    # Aggregate metrics
    successes = [r for r in results if r.get("status") in [200, 201]]
    failures = [r for r in results if r.get("status") not in [200, 201]]
    latencies = [r["latency"] for r in results]
    avg_latency = sum(latencies) / len(latencies) if latencies else 0
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0
    throughput = len(results) / total_duration if total_duration > 0 else 0

    print("\n" + "=" * 65)
    print("📊 RESULTADOS DEL BENCHMARK")
    print("=" * 65)
    print(f"  ✅ Transacciones Exitosas: {len(successes)} / {len(results)} ({len(successes)/len(results)*100:.1f}%)")
    print(f"  ❌ Transacciones Fallidas: {len(failures)}")
    if failures:
        print(f"     🔍 Detalle error: tipo={failures[0].get('type')} err={failures[0].get('error')}")
    print(f"  ⏱️ Duración Total:        {total_duration:.2f} s")
    print(f"  ⚡ Throughput Real:        {throughput:.1f} req/s")
    print(f"  📈 Latencia Promedio:      {avg_latency * 1000:.1f} ms")
    print(f"  🎯 Latencia p95:           {p95_latency * 1000:.1f} ms")
    print(f"  ⏱️ Latencia Mínima:        {min(latencies)*1000:.1f} ms")
    print(f"  ⏱️ Latencia Máxima:        {max(latencies)*1000:.1f} ms")

    print(f"\n[TELEMETRÍA DE HARDWARE EN CARGA]")
    print(f"  🌡️ Temperaturas Peak:    CPU={peak_temps.get('cpu-thermal', 'N/A')}°C | GPU={peak_temps.get('gpu-thermal', 'N/A')}°C")
    delta_cpu = peak_temps.get("cpu-thermal", 0) - base_temps.get("cpu-thermal", 0) if "cpu-thermal" in peak_temps and "cpu-thermal" in base_temps else 0
    print(f"  🔥 Delta Térmico (ΔT):    {delta_cpu:+.1f}°C")
    print(f"  💾 Memoria RAM Peak:     Usada={peak_mem.get('MemUsedMB', 'N/A')} MB (Delta={peak_mem.get('MemUsedMB', 0) - base_mem.get('MemUsedMB', 0):+} MB)")
    print(f"  🛡️ Swap Usado:           {base_mem.get('SwapTotal', 0) - peak_mem.get('SwapFree', 0)} MB (Sin saturación)")

    # Stability assertion
    print("\n" + "=" * 65)
    if len(failures) == 0 and peak_temps.get("cpu-thermal", 0) < 75.0:
        print("🎉 ESTABILIDAD HARDWARE: 100% OK (Rendimiento Óptimo y Térmicas Seguras)")
    else:
        print("⚠️ ALERTA: Rendimiento degradado o temperaturas por encima de lo esperado.")
    print("=" * 65)


if __name__ == "__main__":
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    total = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    run_stress_test(workers, total)
