"""
clip_labeler.py — BioMedCLIP sobre Jetson para mejora de etiquetado y prompt engineering.

Tres usos principales:
  1. label_image()    — clasifica una imagen contra un set de candidatos de texto
  2. rank_prompts()   — dado un prompt base y variantes, rankea cuál describe mejor la imagen
  3. embed_image()    — embedding visual para búsqueda por similitud

Modelo: microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224 (via open_clip)
GPU: CUDA (Jetson Orin/AGX). Fallback a CPU si no hay CUDA.
"""

from __future__ import annotations
import logging
import json
from pathlib import Path
from typing import Optional
import numpy as np

logger = logging.getLogger("CLIPLabeler")

# ── Lazy load del modelo (solo cuando se use por primera vez) ─────────────────

_model = None
_preprocess = None
_tokenizer = None
_device = None

def _load_model():
    global _model, _preprocess, _tokenizer, _device

    if _model is not None:
        return

    try:
        import torch
        import open_clip

        _device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"[CLIPLabeler] Cargando BioMedCLIP en {_device}...")

        # BioMedCLIP usa el checkpoint de HuggingFace vía open_clip
        _model, _, _preprocess = open_clip.create_model_and_transforms(
            "hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224"
        )
        _tokenizer = open_clip.get_tokenizer(
            "hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224"
        )
        _model = _model.to(_device)
        _model.eval()
        logger.info("[CLIPLabeler] BioMedCLIP listo.")

    except ImportError as e:
        raise ImportError(
            f"Dependencias faltantes para CLIPLabeler: {e}. "
            "Instalá: pip install open_clip_torch torch torchvision"
        ) from e


def _load_image(image_path: str | Path):
    """Carga y preprocesa una imagen con el transform de BioMedCLIP."""
    from PIL import Image
    import torch

    img = Image.open(image_path).convert("RGB")
    return _preprocess(img).unsqueeze(0).to(_device)


def _encode_texts(texts: list[str]):
    """Tokeniza y codifica un batch de textos."""
    import torch

    tokens = _tokenizer(texts).to(_device)
    with torch.no_grad():
        return _model.encode_text(tokens)


def _encode_image(image_path: str | Path):
    """Codifica una imagen como embedding."""
    import torch

    img_tensor = _load_image(image_path)
    with torch.no_grad():
        return _model.encode_image(img_tensor)


def _cosine_similarities(image_emb, text_embs) -> list[float]:
    """Calcula similitud coseno entre un embedding de imagen y varios de texto."""
    import torch
    import torch.nn.functional as F

    image_emb = F.normalize(image_emb, dim=-1)
    text_embs  = F.normalize(text_embs,  dim=-1)
    sims = (image_emb @ text_embs.T).squeeze(0)
    return sims.cpu().float().tolist()


# ── API pública ────────────────────────────────────────────────────────────────

def label_image(
    image_path: str | Path,
    candidates: list[str],
    top_k: int = 5,
) -> list[dict]:
    """
    Clasifica una imagen médica contra una lista de etiquetas candidatas.

    Args:
        image_path: ruta a la imagen (JPG/PNG/DICOM convertido a imagen)
        candidates: lista de labels en lenguaje natural, ej:
                    ["nódulo pulmonar", "derrame pleural", "cardiomegalia", "normal"]
        top_k: cuántos candidatos retornar

    Returns:
        Lista ordenada de {"label": str, "score": float} con los top_k más similares.

    Uso en etiquetado:
        Cuando un médico va a etiquetar un estudio, llamá label_image() para pre-sugerir
        los labels más probables según BioMedCLIP. El médico confirma o corrige.
    """
    _load_model()

    # Prefijo biomédico mejora la calibración de BioMedCLIP
    prefixed = [f"an image of {c}" for c in candidates]

    text_embs = _encode_texts(prefixed)
    image_emb = _encode_image(image_path)
    scores = _cosine_similarities(image_emb, text_embs)

    ranked = sorted(
        [{"label": candidates[i], "score": round(scores[i], 4)} for i in range(len(candidates))],
        key=lambda x: x["score"],
        reverse=True,
    )
    return ranked[:top_k]


def rank_prompts(
    image_path: str | Path,
    prompts: list[str],
) -> list[dict]:
    """
    Dado un conjunto de variantes de prompt, rankea cuál describe mejor la imagen.

    Uso principal: prompt engineering.
    Si querés saber si "nódulo pulmonar de 8mm" describe mejor la imagen que
    "masa pulmonar" o "consolidación", pasás las 3 variantes y obtenés el ranking.

    Returns:
        Lista ordenada de {"prompt": str, "score": float}.
    """
    _load_model()

    text_embs = _encode_texts(prompts)
    image_emb = _encode_image(image_path)
    scores = _cosine_similarities(image_emb, text_embs)

    ranked = sorted(
        [{"prompt": prompts[i], "score": round(scores[i], 4)} for i in range(len(prompts))],
        key=lambda x: x["score"],
        reverse=True,
    )
    return ranked


def embed_image(image_path: str | Path) -> list[float]:
    """
    Retorna el embedding visual normalizado (512-dim para BioMedCLIP).

    Uso: búsqueda por similitud entre estudios — encontrá casos similares
    en el historial local para contextualizar el análisis RAG.
    """
    _load_model()

    import torch.nn.functional as F
    emb = _encode_image(image_path)
    emb = F.normalize(emb, dim=-1)
    return emb.squeeze(0).cpu().float().tolist()


def find_similar_studies(
    image_path: str | Path,
    study_embeddings: list[dict],  # [{"study_id": int, "embedding": list[float]}]
    top_k: int = 3,
) -> list[dict]:
    """
    Encuentra los estudios más similares visualmente usando embeddings CLIP almacenados.

    Args:
        study_embeddings: embeddings pre-calculados de estudios anteriores.
                         Guardá estos en SQLite cuando procesés un estudio.

    Returns:
        Top-K estudios más similares con {"study_id", "similarity"}.
    """
    import numpy as np

    query_emb = np.array(embed_image(image_path))

    results = []
    for s in study_embeddings:
        ref = np.array(s["embedding"])
        sim = float(np.dot(query_emb, ref) / (np.linalg.norm(query_emb) * np.linalg.norm(ref) + 1e-8))
        results.append({"study_id": s["study_id"], "similarity": round(sim, 4)})

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:top_k]


# ── Labels predefinidos por especialidad ──────────────────────────────────────

SPECIALTY_LABELS: dict[str, list[str]] = {
    "ecografia_abdominal": [
        "hígado normal", "hígado con lesión focal", "hígado con esteatosis",
        "colelitiasis", "colecistitis aguda", "vesícula biliar normal",
        "dilatación de la vía biliar", "páncreas normal", "pancreatitis",
        "bazo aumentado de tamaño", "riñón con litiasis", "riñón normal",
        "ascitis", "derrame peritoneal", "tumor retroperitoneal",
    ],
    "radiografia_torax": [
        "tórax normal", "cardiomegalia", "derrame pleural", "neumotórax",
        "consolidación pulmonar", "nódulo pulmonar", "masa pulmonar",
        "atelectasia", "enfisema", "edema pulmonar", "tuberculosis pulmonar",
        "fracturas costales", "ensanchamiento mediastínico",
    ],
    "ecografia_obstetrica": [
        "embarazo normal", "placenta previa", "oligoamnios", "polihidramnios",
        "restricción del crecimiento intrauterino", "malformación fetal",
        "gemelos", "líquido amniótico normal", "latido cardíaco fetal normal",
    ],
    "electrocardiograma": [
        "ritmo sinusal normal", "fibrilación auricular", "taquicardia sinusal",
        "bloqueo de rama izquierda", "bloqueo de rama derecha",
        "elevación del ST", "depresión del ST", "hipertrofia ventricular izquierda",
        "extrasístoles ventriculares", "QT prolongado",
    ],
    "general": [
        "imagen normal", "hallazgo patológico", "hallazgo crítico",
        "requiere seguimiento", "normal con variantes anatómicas",
    ],
}


def label_by_specialty(
    image_path: str | Path,
    specialty: str,
    top_k: int = 5,
    extra_candidates: Optional[list[str]] = None,
) -> list[dict]:
    """
    Clasifica una imagen usando el set de labels predefinidos para la especialidad.
    Admite `extra_candidates` para agregar labels personalizados del dataset de CEGIN.
    """
    candidates = SPECIALTY_LABELS.get(specialty.lower(), SPECIALTY_LABELS["general"]).copy()
    if extra_candidates:
        candidates.extend(extra_candidates)

    return label_image(image_path, candidates, top_k=top_k)


# ── Adaptador para el pipeline de análisis clínico ────────────────────────────

_SPECIALTY_META: dict[str, tuple[str, str]] = {
    "ecografia_abdominal": ("abdomen", "ecografía"),
    "radiografia_torax": ("tórax", "radiografía"),
    "ecografia_obstetrica": ("pelvis/obstétrico", "ecografía"),
    "electrocardiograma": ("cardíaco", "electrocardiograma"),
    "general": ("general", "imagen"),
}


def classify_visual_findings(image_path: str | Path, specialty: str = "general", top_k: int = 5) -> dict:
    """
    Adapta label_by_specialty() al formato de "hallazgos visuales" que consume
    el pipeline de análisis clínico (vision_service.py: extract_visual_findings).
    """
    results = label_by_specialty(image_path, specialty, top_k=top_k)
    if not results:
        raise RuntimeError("BioMedCLIP no devolvió resultados de clasificación")

    top = results[0]
    anomalies = [r["label"] for r in results if "normal" not in r["label"].lower()][:3]
    body_region, modality = _SPECIALTY_META.get(specialty.lower(), _SPECIALTY_META["general"])

    return {
        "finding": f"Hallazgo predominante (BioMedCLIP local): {top['label']}.",
        # score es similitud coseno de CLIP, no una probabilidad calibrada — se usa como proxy de confianza
        "confidence": top["score"],
        "anomalies": anomalies,
        "body_region": body_region,
        "modality": modality,
    }


def warmup() -> None:
    """Precarga el modelo BioMedCLIP en memoria (llamar al arrancar el servicio)."""
    _load_model()
