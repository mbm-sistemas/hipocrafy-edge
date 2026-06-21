"""
routes_clip.py — Endpoints BioMedCLIP para etiquetado y prompt engineering.

Estos endpoints son llamados desde:
  - El panel de etiquetado ML del médico (frontend /medico/etiquetado)
  - Scripts de optimización de prompts en desarrollo

NO requieren autenticación JWT del cloud (corren en red interna del Jetson).
"""

from __future__ import annotations
import tempfile
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/clip", tags=["BioMedCLIP"])


def _save_temp(file: UploadFile) -> Path:
    suffix = Path(file.filename or "img.jpg").suffix or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(file.file.read())
    tmp.close()
    return Path(tmp.name)


# ── 1. Clasificación por etiquetas candidatas ─────────────────────────────────

@router.post("/label")
async def label_image_endpoint(
    image: UploadFile = File(...),
    specialty: str  = Form("general"),
    top_k:     int  = Form(5),
    extra_labels: str = Form(""),      # JSON array string: ["hallazgo x", "hallazgo y"]
):
    """
    Clasifica una imagen médica contra los labels predefinidos de la especialidad
    + cualquier label personalizado enviado en extra_labels.

    Respuesta:
        [{"label": "...", "score": 0.84}, ...]  ordenados de mayor a menor similitud.
    """
    try:
        from clip_labeler import label_by_specialty
    except ImportError as e:
        raise HTTPException(503, f"BioMedCLIP no disponible: {e}")

    extra = []
    if extra_labels.strip():
        try:
            import json
            extra = json.loads(extra_labels)
        except Exception:
            pass

    tmp = _save_temp(image)
    try:
        results = label_by_specialty(str(tmp), specialty, top_k=top_k, extra_candidates=extra or None)
        return JSONResponse({"labels": results, "specialty": specialty})
    finally:
        tmp.unlink(missing_ok=True)


# ── 2. Ranking de prompts (prompt engineering) ────────────────────────────────

class PromptRankRequest(BaseModel):
    image_base64: str
    prompts: list[str]

@router.post("/rank-prompts")
async def rank_prompts_endpoint(
    image: UploadFile = File(...),
    prompts_json: str = Form(...),    # JSON array: ["prompt A", "prompt B"]
):
    """
    Rankea variantes de prompt contra la imagen.

    Caso de uso: ¿"nódulo pulmonar de 8mm" describe mejor esta imagen que
    "consolidación pulmonar" o "masa pulmonar"? Pasás las variantes y obtenés
    cuál tiene mayor similitud con la imagen real.

    Útil para iterar prompts del modelo de análisis sin necesidad de re-entrenar.
    """
    try:
        from clip_labeler import rank_prompts
    except ImportError as e:
        raise HTTPException(503, f"BioMedCLIP no disponible: {e}")

    import json
    try:
        prompts = json.loads(prompts_json)
    except Exception:
        raise HTTPException(400, "prompts_json debe ser un array JSON válido")

    if len(prompts) < 2:
        raise HTTPException(400, "Se necesitan al menos 2 prompts para comparar")
    if len(prompts) > 20:
        raise HTTPException(400, "Máximo 20 prompts por llamada")

    tmp = _save_temp(image)
    try:
        results = rank_prompts(str(tmp), prompts)
        return JSONResponse({"ranking": results})
    finally:
        tmp.unlink(missing_ok=True)


# ── 3. Embedding de imagen (para búsqueda por similitud) ─────────────────────

@router.post("/embed")
async def embed_image_endpoint(image: UploadFile = File(...)):
    """
    Retorna el embedding visual BioMedCLIP de una imagen (512 dimensiones).

    Los embeddings se pueden guardar en SQLite local para búsqueda de casos similares.
    """
    try:
        from clip_labeler import embed_image
    except ImportError as e:
        raise HTTPException(503, f"BioMedCLIP no disponible: {e}")

    tmp = _save_temp(image)
    try:
        embedding = embed_image(str(tmp))
        return JSONResponse({"embedding": embedding, "dimensions": len(embedding)})
    finally:
        tmp.unlink(missing_ok=True)
