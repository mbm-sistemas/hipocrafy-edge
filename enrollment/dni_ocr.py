"""
OCR para DNI argentino usando PaddleOCR PP-OCRv4 + OpenCV.

Soporta DNIs nuevos (azul, desde 2012) y viejos (verde).
Detecta automáticamente si es frente o dorso por los campos presentes.
"""

import re
import logging
import numpy as np
from typing import TypedDict, Optional
from pathlib import Path

logger = logging.getLogger("hipocrafy.dni_ocr")

# ---------------------------------------------------------------------------
# Tipos de salida
# ---------------------------------------------------------------------------

class DniData(TypedDict):
    lado: str                    # 'frente' | 'dorso' | 'desconocido'
    nombre: Optional[str]
    apellido: Optional[str]
    dni: Optional[str]
    cuil: Optional[str]
    fecha_nacimiento: Optional[str]   # ISO: YYYY-MM-DD
    sexo: Optional[str]               # 'M' | 'F' | 'X'
    domicilio: Optional[str]
    nacionalidad: Optional[str]
    cuil_valido: Optional[bool]
    raw_text: str


# ---------------------------------------------------------------------------
# Carga lazy del modelo para no penalizar el startup del gateway
# ---------------------------------------------------------------------------

_ocr = None

def _get_ocr():
    global _ocr
    if _ocr is None:
        try:
            from paddleocr import PaddleOCR
            # PP-OCRv4 slim — optimizado para CPU/GPU embebida
            _ocr = PaddleOCR(use_angle_cls=True, lang="es", show_log=False,
                             ocr_version="PP-OCRv4", use_gpu=True)
            logger.info("PaddleOCR PP-OCRv4 cargado con GPU.")
        except ImportError:
            raise RuntimeError(
                "PaddleOCR no está instalado. "
                "Ejecutar: pip install paddlepaddle paddleocr"
            )
    return _ocr


# ---------------------------------------------------------------------------
# Preprocesamiento OpenCV
# ---------------------------------------------------------------------------

def _preprocess(img: np.ndarray) -> np.ndarray:
    """
    Aplica deskew + CLAHE para mejorar legibilidad con reflejos y mala iluminación.
    Recibe imagen BGR (numpy array).
    """
    import cv2

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # CLAHE: equalización adaptativa del histograma — reduce el efecto de reflejos
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # Deskew: detectar ángulo de rotación y corregir
    coords = np.column_stack(np.where(gray < 200))
    if len(coords) > 100:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) > 0.5:
            h, w = gray.shape
            M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
            gray = cv2.warpAffine(gray, M, (w, h),
                                  flags=cv2.INTER_CUBIC,
                                  borderMode=cv2.BORDER_REPLICATE)

    # Devuelve BGR para PaddleOCR
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)


# ---------------------------------------------------------------------------
# Parsers de campos
# ---------------------------------------------------------------------------

_MESES = {
    "ene": "01", "feb": "02", "mar": "03", "abr": "04",
    "may": "05", "jun": "06", "jul": "07", "ago": "08",
    "sep": "09", "oct": "10", "nov": "11", "dic": "12",
}

def _parse_fecha(text: str) -> Optional[str]:
    """Convierte fechas de DNI a ISO YYYY-MM-DD."""
    # Formato DD/MM/AAAA o DD-MM-AAAA
    m = re.search(r"(\d{2})[/\-](\d{2})[/\-](\d{4})", text)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    # Formato DD MMM AAAA (ej: 15 ENE 1990)
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", text)
    if m:
        mes = _MESES.get(m.group(2).lower())
        if mes:
            return f"{m.group(3)}-{mes}-{m.group(1).zfill(2)}"
    return None


def _parse_dni_number(text: str) -> Optional[str]:
    """Extrae el número de DNI (7–8 dígitos, posiblemente con puntos)."""
    m = re.search(r"\b(\d{1,3}\.?\d{3}\.?\d{3})\b", text)
    if m:
        return re.sub(r"\.", "", m.group(1))
    return None


def _validate_cuil(cuil: str) -> bool:
    """Valida el dígito verificador del CUIL/CUIT argentino."""
    digits = re.sub(r"[^0-9]", "", cuil)
    if len(digits) != 11:
        return False
    weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    total = sum(int(digits[i]) * weights[i] for i in range(10))
    remainder = 11 - (total % 11)
    check = 0 if remainder == 11 else (9 if remainder == 10 else remainder)
    return check == int(digits[10])


def _parse_cuil(text: str) -> tuple[Optional[str], Optional[bool]]:
    m = re.search(r"\b(\d{2}[-\s]?\d{7,8}[-\s]?\d{1})\b", text)
    if m:
        raw = m.group(1)
        cuil = re.sub(r"[\s\-]", "", raw)
        if len(cuil) == 11:
            return cuil, _validate_cuil(cuil)
    return None, None


# ---------------------------------------------------------------------------
# Detección frente / dorso y extracción de campos
# ---------------------------------------------------------------------------

_KEYWORDS_FRENTE = {"apellido", "nombres", "nombre", "sexo", "nacionalidad",
                    "ejemplar", "república argentina", "argentina"}
_KEYWORDS_DORSO  = {"domicilio", "cuil", "nacimiento", "municipio", "provincia",
                    "tramite", "trámite", "nro. tramite"}


def _detect_lado(text_lower: str) -> str:
    front_hits = sum(1 for k in _KEYWORDS_FRENTE if k in text_lower)
    back_hits  = sum(1 for k in _KEYWORDS_DORSO  if k in text_lower)
    if front_hits > back_hits:
        return "frente"
    if back_hits > front_hits:
        return "dorso"
    return "desconocido"


def _extract_fields(lines: list[str], lado: str) -> dict:
    text = " ".join(lines)
    text_lower = text.lower()
    result: dict = {}

    if lado == "frente":
        # Apellido: línea que sigue al encabezado "APELLIDO"
        for i, line in enumerate(lines):
            if "apellido" in line.lower() and i + 1 < len(lines):
                result["apellido"] = lines[i + 1].strip().title()
                break

        # Nombres
        for i, line in enumerate(lines):
            if re.search(r"\bnombre", line.lower()) and i + 1 < len(lines):
                result["nombre"] = lines[i + 1].strip().title()
                break

        # Sexo
        m = re.search(r"\b(F|M|X)\b", text)
        if m:
            result["sexo"] = m.group(1)

        # Nacionalidad
        for i, line in enumerate(lines):
            if "nacionalidad" in line.lower() and i + 1 < len(lines):
                result["nacionalidad"] = lines[i + 1].strip().title()
                break

        # Número de DNI (aparece en frente también)
        dni = _parse_dni_number(text)
        if dni:
            result["dni"] = dni

        # Fecha de nacimiento (en frente aparece como "FECHA DE NACIMIENTO")
        for i, line in enumerate(lines):
            if "nacimiento" in line.lower():
                fecha = _parse_fecha(line) or (
                    _parse_fecha(lines[i + 1]) if i + 1 < len(lines) else None
                )
                if fecha:
                    result["fecha_nacimiento"] = fecha
                    break

    else:  # dorso
        # CUIL
        cuil, cuil_valido = _parse_cuil(text)
        if cuil:
            result["cuil"] = cuil
            result["cuil_valido"] = cuil_valido

        # Domicilio: línea que sigue al encabezado "DOMICILIO"
        for i, line in enumerate(lines):
            if "domicilio" in line.lower() and i + 1 < len(lines):
                result["domicilio"] = lines[i + 1].strip().title()
                break

        # Fecha de nacimiento (también aparece en dorso)
        fecha = _parse_fecha(text)
        if fecha:
            result["fecha_nacimiento"] = fecha

        # DNI en dorso (a veces repetido en el código de barras o MRZ)
        dni = _parse_dni_number(text)
        if dni:
            result["dni"] = dni

    return result


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def ocr_dni(image_bytes: bytes) -> DniData:
    """
    Recibe los bytes de una imagen de DNI (JPG/PNG) y retorna DniData.
    Funciona offline — todo el procesamiento es local en el Jetson.
    """
    import cv2

    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("No se pudo decodificar la imagen.")

    preprocessed = _preprocess(img)

    ocr = _get_ocr()
    result = ocr.ocr(preprocessed, cls=True)

    lines: list[str] = []
    for block in (result or [[]]):
        for item in (block or []):
            if item and len(item) >= 2:
                text_conf = item[1]
                if text_conf and text_conf[1] > 0.5:  # confianza mínima 50%
                    lines.append(str(text_conf[0]).strip())

    raw_text = " | ".join(lines)
    lado = _detect_lado(raw_text.lower())
    fields = _extract_fields(lines, lado)

    return DniData(
        lado=lado,
        nombre=fields.get("nombre"),
        apellido=fields.get("apellido"),
        dni=fields.get("dni"),
        cuil=fields.get("cuil"),
        fecha_nacimiento=fields.get("fecha_nacimiento"),
        sexo=fields.get("sexo"),
        domicilio=fields.get("domicilio"),
        nacionalidad=fields.get("nacionalidad"),
        cuil_valido=fields.get("cuil_valido"),
        raw_text=raw_text,
    )
