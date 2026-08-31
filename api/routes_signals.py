"""
FastAPI Router para Signos Vitales, Antropometría y Electrofisiología (ECG/EEG) — Hipocrafy Edge
"""

import logging
from typing import Dict, Any
from fastapi import APIRouter, HTTPException, BackgroundTasks
from services.vitals_service import process_vitals_payload
from services.electrophysiology_service import analyze_ecg_signal, analyze_eeg_signal
from services.sync_service import sync_service

logger = logging.getLogger("HipocrafySignalsAPI")

router = APIRouter(prefix="/api", tags=["Signals & Electrophysiology"])


@router.post("/vitals/ingest")
async def ingest_vitals(payload: Dict[str, Any], background_tasks: BackgroundTasks):
    """
    Ingesta de signos vitales y antropometría (Talla, Peso, IMC, BSA, NEWS2).
    """
    try:
        processed = process_vitals_payload(payload)
        logger.info(f"[*] Signos vitales procesados para DNI {processed['patient_dni']}. Score NEWS2: {processed['news2']['news2_score']}")
        
        # Disparar sincronización asíncrona hacia el backend
        background_tasks.add_task(sync_service.sync_vitals_to_cloud, processed)
        
        return {
            "status": "success",
            "message": "Signos vitales y antropometría registrados correctamente",
            "data": processed
        }
    except Exception as e:
        logger.error(f"Error procesando signos vitales: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ecg/process")
async def process_ecg(payload: Dict[str, Any], background_tasks: BackgroundTasks):
    """
    Procesamiento de electrocardiograma 1D (ECG 12 derivaciones).
    """
    try:
        patient_dni = str(payload.get("patient_dni", ""))
        analyzed = analyze_ecg_signal(payload)
        analyzed["patient_dni"] = patient_dni
        
        logger.info(f"[*] ECG procesado para DNI {patient_dni}. Severidad: {analyzed['overall_severity']}")
        
        background_tasks.add_task(sync_service.sync_signal_to_cloud, "ECG", analyzed)
        
        return {
            "status": "success",
            "message": "Electrocardiograma analizado correctamente",
            "data": analyzed
        }
    except Exception as e:
        logger.error(f"Error procesando ECG: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/eeg/process")
async def process_eeg(payload: Dict[str, Any], background_tasks: BackgroundTasks):
    """
    Procesamiento de electroencefalograma (EEG Multicanal / EDF+).
    """
    try:
        patient_dni = str(payload.get("patient_dni", ""))
        analyzed = analyze_eeg_signal(payload)
        analyzed["patient_dni"] = patient_dni
        
        logger.info(f"[*] EEG procesado para DNI {patient_dni}. Severidad: {analyzed['overall_severity']}")
        
        background_tasks.add_task(sync_service.sync_signal_to_cloud, "EEG", analyzed)
        
        return {
            "status": "success",
            "message": "Electroencefalograma analizado correctamente",
            "data": analyzed
        }
    except Exception as e:
        logger.error(f"Error procesando EEG: {e}")
        raise HTTPException(status_code=500, detail=str(e))
