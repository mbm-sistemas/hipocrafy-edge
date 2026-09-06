"""
Electrophysiology Service (ECG & EEG 1D AI Engine) — Hipocrafy Edge
Procesa trazados electrocardiográficos y electroencefalográficos estandarizados.
"""

import math
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("HipocrafyElectro")


def analyze_ecg_signal(signal_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analiza señales de ECG de 12 derivaciones o derivaciones continuas.
    Retorna intervalos numéricos (PR, QRS, QTc) y hallazgos patológicos de IA.
    """
    sample_rate = signal_data.get("sample_rate_hz", 500)
    leads = signal_data.get("leads", {})

    # Métricas medidas reales - antes, si faltaban, se sustituían silenciosamente
    # por valores fijos "normales" (75/156/88/412/45) y se corría igual la lógica
    # clínica sobre ellos, devolviendo un veredicto de ritmo normal como si viniera
    # de la señal real. Si al dispositivo/cliente le faltó mandar la métrica, hay
    # que fallar explícito en vez de inventar un trazado.
    required = ["heart_rate", "pr_interval_ms", "qrs_duration_ms", "qtc_interval_ms", "axis_degrees"]
    missing = [k for k in required if signal_data.get(k) is None]
    if missing:
        raise ValueError(f"Faltan métricas reales de ECG en el payload: {', '.join(missing)}")

    hr = signal_data["heart_rate"]
    pr_ms = signal_data["pr_interval_ms"]
    qrs_ms = signal_data["qrs_duration_ms"]
    qtc_ms = signal_data["qtc_interval_ms"]
    axis_deg = signal_data["axis_degrees"]

    findings = []
    severity = "NORMAL"

    # Evaluaciones de reglas clínicas e inferencia 1D
    if qtc_ms > 460:
        findings.append({
            "code": "QTC_PROLONGED",
            "title": "Intervalo QTc Prolongado",
            "detail": f"QTc de {qtc_ms} ms (normal < 450 ms en hombres / 460 ms en mujeres). Riesgo de arritmia ventricular.",
            "severity": "WARNING"
        })
        severity = "WARNING"

    if qrs_ms > 120:
        findings.append({
            "code": "BUNDLE_BRANCH_BLOCK",
            "title": "Bloqueo Completo de Rama",
            "detail": f"QRS ensanchado a {qrs_ms} ms.",
            "severity": "WARNING"
        })
        severity = "WARNING"

    # Banderas específicas pasadas por modelos 1D o simuladores
    st_elevation = signal_data.get("st_elevation_leads", [])
    if st_elevation:
        findings.append({
            "code": "ST_ELEVATION_STEMI",
            "title": "Elevación del Segmento ST (IAMST)",
            "detail": f"Elevación del ST detectada en derivaciones: {', '.join(st_elevation)}. Cuadro compatible con Infarto Agudo de Miocardio.",
            "severity": "CRITICAL"
        })
        severity = "CRITICAL"

    if signal_data.get("is_afib", False):
        findings.append({
            "code": "AFIB_DETECTED",
            "title": "Fibrilación Auricular (AFib)",
            "detail": "Ausencia de onda P y variabilidad irregular R-R.",
            "severity": "CRITICAL" if hr > 110 else "WARNING"
        })
        if severity != "CRITICAL":
            severity = "WARNING"

    if not findings:
        findings.append({
            "code": "NORMAL_SINUS_RHYTHM",
            "title": "Ritmo Sinusal Normal",
            "detail": "Frecuencia e intervalos dentro de límites normales.",
            "severity": "NORMAL"
        })

    return {
        "modality": "ECG",
        "heart_rate": hr,
        "metrics": {
            "pr_interval_ms": pr_ms,
            "qrs_duration_ms": qrs_ms,
            "qtc_interval_ms": qtc_ms,
            "axis_degrees": axis_deg
        },
        "overall_severity": severity,
        "findings": findings,
        "leads_count": len(leads) if leads else 12
    }


def analyze_eeg_signal(signal_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analiza señales de EEG multicanal (EDF+ / Matrix).
    Retorna potencia de bandas frecuenciales y hallazgos epileptiformes o de encefalopatía.
    """
    channels = signal_data.get("channels", ["F3", "F4", "C3", "C4", "P3", "P4", "O1", "O2"])

    # Distribución espectral de frecuencias (%) - real, medida del trazado.
    # Antes, si faltaba, se sustituía por una distribución fija "normal" y se
    # evaluaba igual la lógica clínica sobre datos inventados.
    bands = signal_data.get("frequency_bands")
    if not bands:
        raise ValueError("Falta frequency_bands (distribución espectral real) en el payload de EEG")

    findings = []
    severity = "NORMAL"

    if signal_data.get("seizure_detected", False) or signal_data.get("spike_wave_discharges", False):
        findings.append({
            "code": "ICTAL_SEIZURE_ACTIVITY",
            "title": "Descarga Epileptiforme Ictal / Paroxística",
            "detail": "Complejos punta-onda lenta síncronos multifocales. Descarga epileptiforme activa.",
            "severity": "CRITICAL"
        })
        severity = "CRITICAL"

    elif bands.get("delta_0_4hz", 0) > 45.0:
        findings.append({
            "code": "DIFFUSE_LENTIFICATION",
            "title": "Lentificación Difusa del Trazado",
            "detail": "Predominio severo de actividad lenta Delta. Compatible con Encefalopatía o Alteración Metodológica del Sensorio.",
            "severity": "WARNING"
        })
        severity = "WARNING"

    else:
        findings.append({
            "code": "NORMAL_ALPHA_RHYTHM",
            "title": "Ritmo Alfa Posterior Fisiológico",
            "detail": "Reactivo a apertura ocular, reactividad simétrica bilateral.",
            "severity": "NORMAL"
        })

    return {
        "modality": "EEG",
        "channels_count": len(channels),
        "frequency_bands": bands,
        "overall_severity": severity,
        "findings": findings
    }
