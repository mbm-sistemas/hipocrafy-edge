"""
Router de enrollment biométrico para el Jetson edge.

Endpoints:
    POST /api/v1/enrollment/ocr-dni       — OCR del DNI (frente o dorso)
    POST /api/v1/enrollment/face-match    — Liveness + matching DNI ↔ selfie
    POST /api/v1/enrollment/register      — Flujo completo: crea paciente en cloud
    POST /api/v1/enrollment/identify      — Identifica paciente por foto (visitas siguientes)
"""

import os
import logging
import httpx
from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from pydantic import BaseModel
from typing import Optional

from enrollment.dni_ocr import ocr_dni, DniData
from enrollment.liveness import check_liveness
from enrollment.face_match import match_faces, register_embedding, identify_patient

logger = logging.getLogger("hipocrafy.enrollment")

router = APIRouter(prefix="/api/v1/enrollment", tags=["Enrollment Biométrico"])

CLOUD_URL = os.getenv("HIPOCRAFY_CLOUD_URL", "").rstrip("/")
GATEWAY_TOKEN = os.getenv("GATEWAY_API_TOKEN", "")
LIVENESS_THRESHOLD = float(os.getenv("LIVENESS_THRESHOLD", "0.7"))
FACE_MATCH_THRESHOLD = float(os.getenv("FACE_MATCH_THRESHOLD", "0.85"))


# ---------------------------------------------------------------------------
# OCR DNI
# ---------------------------------------------------------------------------

@router.post("/ocr-dni")
async def endpoint_ocr_dni(image: UploadFile = File(...)):
    """
    Recibe una imagen del DNI (frente o dorso) y retorna los campos extraídos.
    Detecta automáticamente qué cara del DNI es.
    """
    image_bytes = await image.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="Imagen vacía.")
    try:
        data = ocr_dni(image_bytes)
        return data
    except Exception as e:
        logger.error(f"OCR DNI error: {e}")
        raise HTTPException(status_code=500, detail=f"Error al procesar DNI: {str(e)}")


# ---------------------------------------------------------------------------
# Liveness + Face Match
# ---------------------------------------------------------------------------

@router.post("/face-match")
async def endpoint_face_match(
    dni_image: UploadFile = File(..., description="Imagen del frente del DNI"),
    selfie: UploadFile = File(..., description="Selfie capturada en vivo"),
):
    """
    Ejecuta el pipeline completo:
      1. Liveness detection sobre la selfie
      2. Face matching DNI ↔ selfie (solo si liveness pasa)

    El biometric_hash del resultado puede usarse para registrar al paciente en el cloud.
    """
    dni_bytes = await dni_image.read()
    selfie_bytes = await selfie.read()

    if not dni_bytes or not selfie_bytes:
        raise HTTPException(status_code=400, detail="Se requieren ambas imágenes.")

    try:
        liveness = check_liveness(selfie_bytes, threshold=LIVENESS_THRESHOLD)
    except Exception as e:
        logger.error(f"Liveness error: {e}")
        raise HTTPException(status_code=500, detail=f"Error en liveness check: {str(e)}")

    if not liveness["passed"]:
        return {
            "match": False,
            "liveness_passed": False,
            "liveness_score": liveness["score"],
            "message": "Verificación de presencia fallida. Por favor mire directamente a la cámara.",
        }

    try:
        result = match_faces(
            dni_image_bytes=dni_bytes,
            selfie_bytes=selfie_bytes,
            liveness_passed=True,
            threshold=FACE_MATCH_THRESHOLD,
        )
    except Exception as e:
        logger.error(f"Face match error: {e}")
        raise HTTPException(status_code=500, detail=f"Error en verificación facial: {str(e)}")

    return {
        **result,
        "liveness_score": liveness["score"],
        "message": "Verificación exitosa." if result["match"] else "No se pudo verificar la identidad.",
    }


# ---------------------------------------------------------------------------
# Enrollment completo
# ---------------------------------------------------------------------------

@router.post("/register")
async def endpoint_register(
    dni_image: UploadFile = File(...),
    selfie: UploadFile = File(...),
    nombre: str = Form(...),
    apellido: str = Form(...),
    dni_numero: str = Form(...),
    fecha_nacimiento: Optional[str] = Form(None),
    domicilio: Optional[str] = Form(None),
    telefono: Optional[str] = Form(None),
    center_id: int = Form(...),
    consent_given: bool = Form(...),
    oth_token: str = Form(..., description="Bearer token del OTH autenticado"),
):
    """
    Flujo completo de enrollment:
      1. Liveness + face match
      2. Si pasa → registra embedding localmente
      3. Crea el paciente en el cloud (POST /api/oth/patients/enroll)
      4. Almacena embedding en SQLite con el patient_id retornado

    El biometric_hash (no el vector) sube al cloud.
    """
    if not consent_given:
        raise HTTPException(status_code=400, detail="Se requiere consentimiento del paciente.")

    dni_bytes = await dni_image.read()
    selfie_bytes = await selfie.read()

    # Paso 1: Liveness
    liveness = check_liveness(selfie_bytes, threshold=LIVENESS_THRESHOLD)
    if not liveness["passed"]:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "liveness_failed",
                "liveness_score": liveness["score"],
                "message": "Verificación de presencia fallida.",
            }
        )

    # Paso 2: Face match DNI ↔ selfie
    match_result = match_faces(
        dni_image_bytes=dni_bytes,
        selfie_bytes=selfie_bytes,
        liveness_passed=True,
        threshold=FACE_MATCH_THRESHOLD,
    )
    if not match_result["match"]:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "face_mismatch",
                "score": match_result["score"],
                "message": "El rostro no coincide con el DNI.",
            }
        )

    # Paso 3: Crear paciente en cloud
    if not CLOUD_URL or not GATEWAY_TOKEN:
        raise HTTPException(status_code=503, detail="Cloud no configurado en este nodo.")

    cloud_payload = {
        "name": f"{nombre} {apellido}".strip(),
        "dni": dni_numero,
        "fecha_nacimiento": fecha_nacimiento,
        "domicilio": domicilio,
        "telefono": telefono,
        "center_id": center_id,
        "consent_given": True,
        "biometric_hash": match_result["biometric_hash"],
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{CLOUD_URL}/api/oth/patients/enroll",
                json=cloud_payload,
                headers={"Authorization": f"Bearer {oth_token}",
                         "Accept": "application/json"},
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"No se pudo conectar al cloud: {e}")

    if resp.status_code not in (200, 201):
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Error del cloud: {resp.text[:300]}"
        )

    cloud_data = resp.json()
    patient_id = cloud_data["patient_id"]

    # Paso 4: Guardar embedding localmente con el patient_id real
    try:
        register_embedding(patient_id, selfie_bytes)
        logger.info(f"Embedding guardado para paciente {patient_id}.")
    except Exception as e:
        # No es fatal — el paciente quedó creado en el cloud
        logger.warning(f"No se pudo guardar embedding local: {e}")

    return {
        "patient_id": patient_id,
        "name": cloud_data.get("name"),
        "center_id": cloud_data.get("center_id"),
        "center_name": cloud_data.get("center_name"),
        "face_score": match_result["score"],
        "liveness_score": liveness["score"],
        "message": "Paciente registrado exitosamente.",
    }


# ---------------------------------------------------------------------------
# Identificación en visitas siguientes
# ---------------------------------------------------------------------------

@router.post("/identify")
async def endpoint_identify(selfie: UploadFile = File(...)):
    """
    Identifica un paciente que ya fue enrollado comparando su foto
    contra todos los embeddings almacenados en este nodo.
    Umbral más alto (0.90) para reducir falsos positivos.
    """
    selfie_bytes = await selfie.read()
    if not selfie_bytes:
        raise HTTPException(status_code=400, detail="Imagen vacía.")

    # Liveness también en identificación (evita acceso con foto del paciente)
    liveness = check_liveness(selfie_bytes, threshold=LIVENESS_THRESHOLD)
    if not liveness["passed"]:
        return {
            "identified": False,
            "liveness_passed": False,
            "message": "Verificación de presencia fallida.",
        }

    try:
        result = identify_patient(selfie_bytes)
    except Exception as e:
        logger.error(f"Identify error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    if result:
        return {
            "identified": True,
            "patient_id": result["patient_id"],
            "score": result["score"],
            "liveness_passed": True,
            "message": "Paciente identificado.",
        }

    return {
        "identified": False,
        "liveness_passed": True,
        "message": "No se encontró una coincidencia en este nodo.",
    }
