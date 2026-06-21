"""
Face matching DNI ↔ selfie usando InsightFace buffalo_l.

Arquitectura de privacidad:
- Los embeddings faciales se guardan SOLO en SQLite local del Jetson.
- Al cloud sube únicamente el biometric_hash (SHA256 del vector).
- Aunque se comprometa el cloud, los datos biométricos permanecen en territorio.

Pipeline:
    Liveness check (ver liveness.py) → ExtractFace → FaceMatch
"""

import hashlib
import json
import logging
import sqlite3
import numpy as np
from pathlib import Path
from typing import Optional, TypedDict

logger = logging.getLogger("hipocrafy.face_match")

DB_PATH = Path(__file__).parent.parent / "edge_data.db"

# Umbral de similitud coseno para considerar que es la misma persona
DEFAULT_MATCH_THRESHOLD = 0.85


class FaceMatchResult(TypedDict):
    match: bool
    score: float               # similitud coseno 0.0–1.0
    confidence: str            # 'high' | 'medium' | 'low'
    liveness_passed: bool
    biometric_hash: Optional[str]   # SHA256 del embedding — para subir al cloud


# ---------------------------------------------------------------------------
# Carga lazy de InsightFace
# ---------------------------------------------------------------------------

_app = None

def _get_face_app():
    global _app
    if _app is not None:
        return _app
    try:
        from insightface.app import FaceAnalysis
        _app = FaceAnalysis(
            name="buffalo_l",
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
        )
        _app.prepare(ctx_id=0, det_size=(640, 640))
        logger.info("InsightFace buffalo_l cargado con GPU.")
    except ImportError:
        raise RuntimeError("insightface no instalado. Ejecutar: pip install insightface onnxruntime-gpu")
    return _app


# ---------------------------------------------------------------------------
# SQLite: tabla de embeddings biométricos
# ---------------------------------------------------------------------------

def init_biometric_db():
    """Crea la tabla de embeddings si no existe. Llamado desde main.py en startup."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS biometric_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER UNIQUE,
                biometric_hash TEXT UNIQUE,
                embedding BLOB NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_biometric_hash ON biometric_embeddings(biometric_hash)"
        )


def _save_embedding(patient_id: int, embedding: np.ndarray) -> str:
    """Guarda el embedding en SQLite. Retorna el biometric_hash."""
    bio_hash = hashlib.sha256(embedding.tobytes()).hexdigest()
    blob = embedding.astype(np.float32).tobytes()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """INSERT INTO biometric_embeddings (patient_id, biometric_hash, embedding, updated_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(patient_id) DO UPDATE SET
                   biometric_hash = excluded.biometric_hash,
                   embedding = excluded.embedding,
                   updated_at = CURRENT_TIMESTAMP""",
            (patient_id, bio_hash, blob)
        )
    return bio_hash


def _load_all_embeddings() -> list[tuple[int, str, np.ndarray]]:
    """Carga todos los embeddings para identificación en tiempo real."""
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT patient_id, biometric_hash, embedding FROM biometric_embeddings"
        ).fetchall()
    result = []
    for patient_id, bio_hash, blob in rows:
        emb = np.frombuffer(blob, dtype=np.float32)
        result.append((patient_id, bio_hash, emb))
    return result


# ---------------------------------------------------------------------------
# Helpers de embedding
# ---------------------------------------------------------------------------

def _extract_embedding(image_bytes: bytes) -> Optional[np.ndarray]:
    """
    Extrae el embedding del rostro más grande en la imagen.
    Retorna None si no se detecta ningún rostro.
    """
    import cv2
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("No se pudo decodificar la imagen.")

    app = _get_face_app()
    faces = app.get(img)
    if not faces:
        return None

    # Rostro con mayor área de bounding box
    face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    return face.normed_embedding


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))


def _score_to_confidence(score: float) -> str:
    if score >= 0.92:
        return "high"
    if score >= DEFAULT_MATCH_THRESHOLD:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def match_faces(
    dni_image_bytes: bytes,
    selfie_bytes: bytes,
    liveness_passed: bool,
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> FaceMatchResult:
    """
    Compara el rostro del DNI con la selfie capturada en vivo.

    Args:
        dni_image_bytes: imagen del frente del DNI (recortada o completa).
        selfie_bytes: foto capturada por la cámara en el momento del enrollment.
        liveness_passed: resultado previo del check de liveness (debe ser True).
        threshold: similitud mínima para considerar match (default 0.85).

    Returns:
        FaceMatchResult — incluye biometric_hash si hay match.
    """
    if not liveness_passed:
        logger.warning("FaceMatch: liveness no pasado — rechazando sin calcular embedding.")
        return FaceMatchResult(match=False, score=0.0, confidence="low",
                               liveness_passed=False, biometric_hash=None)

    emb_dni = _extract_embedding(dni_image_bytes)
    if emb_dni is None:
        logger.warning("FaceMatch: no se detectó rostro en la imagen del DNI.")
        return FaceMatchResult(match=False, score=0.0, confidence="low",
                               liveness_passed=True, biometric_hash=None)

    emb_selfie = _extract_embedding(selfie_bytes)
    if emb_selfie is None:
        logger.warning("FaceMatch: no se detectó rostro en la selfie.")
        return FaceMatchResult(match=False, score=0.0, confidence="low",
                               liveness_passed=True, biometric_hash=None)

    score = _cosine_similarity(emb_dni, emb_selfie)
    match = score >= threshold
    confidence = _score_to_confidence(score)

    # El hash se genera del embedding de la selfie (la foto de mayor calidad)
    bio_hash = hashlib.sha256(emb_selfie.astype(np.float32).tobytes()).hexdigest() if match else None

    logger.info(f"FaceMatch: score={score:.3f}, match={'✅' if match else '❌'}, confidence={confidence}")

    return FaceMatchResult(
        match=match,
        score=score,
        confidence=confidence,
        liveness_passed=True,
        biometric_hash=bio_hash,
    )


def register_embedding(patient_id: int, selfie_bytes: bytes) -> str:
    """
    Extrae y persiste el embedding de un paciente recién enrollado.
    Retorna el biometric_hash para subir al cloud.
    """
    emb = _extract_embedding(selfie_bytes)
    if emb is None:
        raise ValueError("No se detectó rostro en la selfie para registrar embedding.")
    return _save_embedding(patient_id, emb)


def identify_patient(selfie_bytes: bytes, threshold: float = 0.90) -> Optional[dict]:
    """
    Identifica un paciente comparando la selfie contra todos los embeddings locales.
    Umbral más alto (0.90) para identificación en visitas siguientes.

    Retorna dict con patient_id y score, o None si no hay match.
    """
    emb = _extract_embedding(selfie_bytes)
    if emb is None:
        return None

    candidates = _load_all_embeddings()
    if not candidates:
        return None

    best_score = 0.0
    best_patient_id = None

    for patient_id, bio_hash, stored_emb in candidates:
        score = _cosine_similarity(emb, stored_emb)
        if score > best_score:
            best_score = score
            best_patient_id = patient_id

    if best_score >= threshold:
        logger.info(f"Paciente identificado: id={best_patient_id}, score={best_score:.3f}")
        return {"patient_id": best_patient_id, "score": best_score}

    return None
