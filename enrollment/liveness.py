"""
Liveness detection usando Silent-Face-Anti-Spoofing (ONNX).

Detecta si la imagen capturada es un rostro real (3D) o un ataque de
presentación (foto impresa, pantalla). No requiere cooperación activa
del paciente — no hay challenge de parpadeo ni sonrisa.

El modelo ONNX debe estar en: enrollment/models/liveness.onnx
Descarga: https://github.com/minivision-ai/Silent-Face-Anti-Spoofing
Exportar a ONNX con el script del repositorio original.
"""

import logging
import numpy as np
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger("hipocrafy.liveness")

MODEL_PATH = Path(__file__).parent / "models" / "liveness.onnx"
DEFAULT_THRESHOLD = 0.7   # score mínimo para considerar rostro real
INPUT_SIZE = (80, 80)     # resolución esperada por el modelo MiniVGG


class LivenessResult(TypedDict):
    is_live: bool
    score: float           # 0.0 → spoof, 1.0 → live
    passed: bool           # score >= threshold


# ---------------------------------------------------------------------------
# Carga lazy del modelo ONNX
# ---------------------------------------------------------------------------

_session = None

def _get_session():
    global _session
    if _session is not None:
        return _session

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"Modelo de liveness no encontrado en {MODEL_PATH}. "
            "Descargar Silent-Face-Anti-Spoofing y exportar a ONNX."
        )

    try:
        import onnxruntime as ort
        # Prioriza GPU Jetson (TensorRT EP) → CUDA EP → CPU
        providers = ["TensorrtExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider"]
        _session = ort.InferenceSession(str(MODEL_PATH), providers=providers)
        active = _session.get_providers()[0]
        logger.info(f"Liveness model cargado con provider: {active}")
    except ImportError:
        raise RuntimeError("onnxruntime no instalado. Ejecutar: pip install onnxruntime-gpu")

    return _session


# ---------------------------------------------------------------------------
# Preprocesamiento de imagen para el modelo
# ---------------------------------------------------------------------------

def _preprocess_face(img_bgr: np.ndarray) -> np.ndarray:
    import cv2
    resized = cv2.resize(img_bgr, INPUT_SIZE)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    normalized = rgb.astype(np.float32) / 255.0
    # Normalización ImageNet estándar
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std  = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    normalized = (normalized - mean) / std
    # CHW → NCHW (batch de 1)
    return np.expand_dims(normalized.transpose(2, 0, 1), axis=0)


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def check_liveness(image_bytes: bytes, threshold: float = DEFAULT_THRESHOLD) -> LivenessResult:
    """
    Analiza si la imagen contiene un rostro real o un ataque de presentación.

    Args:
        image_bytes: bytes de la imagen capturada (JPG/PNG).
        threshold: score mínimo para considerar live (default 0.7).

    Returns:
        LivenessResult con score y flag passed.
    """
    import cv2

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("No se pudo decodificar la imagen para liveness.")

    # Detección de rostro con Haar Cascade (rápido, sin GPU)
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60))

    if len(faces) == 0:
        logger.warning("Liveness: no se detectó ningún rostro en la imagen.")
        return LivenessResult(is_live=False, score=0.0, passed=False)

    # Tomar el rostro más grande (más cercano a la cámara)
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    face_crop = img[y:y+h, x:x+w]

    session = _get_session()
    input_name = session.get_inputs()[0].name
    tensor = _preprocess_face(face_crop)

    outputs = session.run(None, {input_name: tensor})
    # El modelo retorna logits [spoof, live]; softmax para obtener probabilidad
    logits = outputs[0][0]
    exp = np.exp(logits - np.max(logits))
    probs = exp / exp.sum()
    live_score = float(probs[1]) if len(probs) > 1 else float(probs[0])

    passed = live_score >= threshold
    logger.info(f"Liveness score: {live_score:.3f} — {'LIVE ✅' if passed else 'SPOOF ❌'}")

    return LivenessResult(is_live=passed, score=live_score, passed=passed)
