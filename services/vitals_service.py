"""
Vitals & Anthropometrics Service — Hipocrafy Edge
Procesa signos vitales, antropometría (Talla, Peso, IMC, BSA) y calcula NEWS2 Score.
"""

import math
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("HipocrafyVitals")


def calculate_bmi(weight_kg: float, height_cm: float) -> Dict[str, Any]:
    """Calcula el Índice de Masa Corporal (IMC) y la Superficie Corporal (BSA - Mosteller)."""
    if height_cm <= 0 or weight_kg <= 0:
        return {"bmi": None, "category": "Desconocido", "bsa_m2": None}
    
    height_m = height_cm / 100.0
    bmi = round(weight_kg / (height_m ** 2), 2)
    
    # BSA Mosteller Formula: sqrt( (height_cm * weight_kg) / 3600 )
    bsa = round(math.sqrt((height_cm * weight_kg) / 3600.0), 2)
    
    if bmi < 18.5:
        category = "Bajo peso"
    elif 18.5 <= bmi < 25.0:
        category = "Normal"
    elif 25.0 <= bmi < 30.0:
        category = "Sobrepeso"
    elif 30.0 <= bmi < 35.0:
        category = "Obesidad Grado I"
    elif 35.0 <= bmi < 40.0:
        category = "Obesidad Grado II"
    else:
        category = "Obesidad Grado III (Mórbida)"
        
    return {
        "bmi": bmi,
        "category": category,
        "bsa_m2": bsa
    }


def calculate_news2_score(vitals: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calcula el National Early Warning Score 2 (NEWS2).
    Score total: 0-4 (Bajo), 5-6 (Medio), >=7 (Alto/Riesgo Crítico).
    """
    score = 0
    breakdown = {}
    
    # 1. Respiración (resp_rate - rpm)
    rr = vitals.get("resp_rate")
    if rr is not None:
        if rr <= 8:
            s = 3
        elif 9 <= rr <= 11:
            s = 1
        elif 12 <= rr <= 20:
            s = 0
        elif 21 <= rr <= 24:
            s = 2
        else:
            s = 3
        score += s
        breakdown["resp_rate"] = s

    # 2. Saturación de Oxígeno (spo2 - %)
    spo2 = vitals.get("spo2")
    if spo2 is not None:
        if spo2 <= 91:
            s = 3
        elif 92 <= spo2 <= 93:
            s = 2
        elif 94 <= spo2 <= 95:
            s = 1
        else:
            s = 0
        score += s
        breakdown["spo2"] = s

    # 3. Presión Arterial Sistólica (sbp - mmHg)
    sbp = vitals.get("sbp")
    if sbp is not None:
        if sbp <= 90:
            s = 3
        elif 91 <= sbp <= 100:
            s = 2
        elif 101 <= sbp <= 110:
            s = 1
        elif 111 <= sbp <= 219:
            s = 0
        else:
            s = 3
        score += s
        breakdown["sbp"] = s

    # 4. Frecuencia Cardíaca (heart_rate - bpm)
    hr = vitals.get("heart_rate")
    if hr is not None:
        if hr <= 40:
            s = 3
        elif 41 <= hr <= 50:
            s = 1
        elif 51 <= hr <= 90:
            s = 0
        elif 91 <= hr <= 110:
            s = 1
        elif 111 <= hr <= 130:
            s = 2
        else:
            s = 3
        score += s
        breakdown["heart_rate"] = s

    # 5. Temperatura (temp_c - °C)
    temp = vitals.get("temp_c")
    if temp is not None:
        if temp <= 35.0:
            s = 3
        elif 35.1 <= temp <= 36.0:
            s = 1
        elif 36.1 <= temp <= 38.0:
            s = 0
        elif 38.1 <= temp <= 39.0:
            s = 1
        else:
            s = 2
        score += s
        breakdown["temp_c"] = s

    # Determinar nivel de riesgo
    if score >= 7:
        risk_level = "CRÍTICO"
        action = "Respuesta clínica de emergencia inmediata / Derivación a UCO-UTI."
    elif score >= 5 or any(v == 3 for v in breakdown.values()):
        risk_level = "MEDIO-ALTO"
        action = "Revisión urgente por médico internista o de guardia."
    else:
        risk_level = "BAJO"
        action = "Monitoreo de rutina por enfermería."

    return {
        "news2_score": score,
        "risk_level": risk_level,
        "action_required": action,
        "breakdown": breakdown
    }


def process_vitals_payload(raw_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza el payload de signos vitales + antropometría al Estándar Hipocrafy.
    """
    height_cm = raw_data.get("height_cm") or raw_data.get("talla_cm")
    weight_kg = raw_data.get("weight_kg") or raw_data.get("peso_kg")
    
    anthropometrics = {}
    if height_cm and weight_kg:
        anthropometrics = calculate_bmi(float(weight_kg), float(height_cm))
        anthropometrics["height_cm"] = float(height_cm)
        anthropometrics["weight_kg"] = float(weight_kg)

    vitals = {
        "heart_rate": raw_data.get("heart_rate") or raw_data.get("fc"),
        "sbp": raw_data.get("sbp") or raw_data.get("pa_sistolica"),
        "dbp": raw_data.get("dbp") or raw_data.get("pa_diastolica"),
        "map": raw_data.get("map") or raw_data.get("pa_media"),
        "spo2": raw_data.get("spo2") or raw_data.get("saturacion"),
        "temp_c": raw_data.get("temp_c") or raw_data.get("temperatura"),
        "resp_rate": raw_data.get("resp_rate") or raw_data.get("fr")
    }

    # Eliminar valores None de vitals
    vitals = {k: float(v) for k, v in vitals.items() if v is not None}
    
    news2 = calculate_news2_score(vitals)

    return {
        "patient_dni": str(raw_data.get("patient_dni", "")),
        "vitals": vitals,
        "anthropometrics": anthropometrics,
        "news2": news2,
        "timestamp": raw_data.get("timestamp")
    }
