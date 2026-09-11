"""
cine_extractor.py — Hipocrafy Edge

Detecta si una instancia DICOM trae más de un frame (cine-loop típico de
ecografía: latido cardíaco, Doppler, etc.) y, si es así, extrae un MP4 real
en vez de quedarse con una sola foto del medio de la serie.

Regla dura: nunca se inventa nada. Si no se puede extraer un video real
(falta ffmpeg, transfer syntax no soportado, el frame de decodificación
falla), la función devuelve None y el caller sigue tratando la instancia
como imagen estática — no se genera un archivo de video corrupto ni un
FPS "preciso" que en realidad es un invento.
"""

import logging
import os
import subprocess
import tempfile
from typing import Optional

import numpy as np
import pydicom

logger = logging.getLogger("HipocrafyCineExtractor")

# Transfer syntaxes de video ya codificado (MPEG2/H.264) encapsulado en el DICOM.
_VIDEO_TRANSFER_SYNTAXES = {
    "1.2.840.10008.1.2.4.100",  # MPEG2 Main Profile @ Main Level
    "1.2.840.10008.1.2.4.101",  # MPEG2 Main Profile @ High Level
    "1.2.840.10008.1.2.4.102",  # MPEG-4 AVC/H.264 High Profile
    "1.2.840.10008.1.2.4.103",  # MPEG-4 AVC/H.264 BD-compatible
    "1.2.840.10008.1.2.4.104",  # MPEG-4 AVC/H.264 High Profile 2D
    "1.2.840.10008.1.2.4.105",  # MPEG-4 AVC/H.264 High Profile 3D
    "1.2.840.10008.1.2.4.106",  # MPEG-4 AVC/H.264 Stereo High Profile
}

# Usado SOLO si el DICOM no trae CineRate/FrameTime/RecommendedDisplayFrameRate.
# Se marca fps_is_estimated=True cada vez que se usa — nunca se presenta como
# el valor real del equipo.
DEFAULT_FPS = 15.0

FFMPEG_TIMEOUT_SECONDS = 180


def classify_instance(ds: pydicom.Dataset) -> tuple[str, Optional[int]]:
    """Devuelve ('image' | 'multiframe' | 'video', frame_count)."""
    frame_count = int(getattr(ds, "NumberOfFrames", 1) or 1)
    transfer_syntax = str(getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", ""))

    if transfer_syntax in _VIDEO_TRANSFER_SYNTAXES:
        return "video", frame_count if frame_count > 1 else None
    if frame_count > 1:
        return "multiframe", frame_count
    return "image", None


def _estimate_fps(ds: pydicom.Dataset) -> tuple[float, bool]:
    """Devuelve (fps, fps_is_estimated)."""
    for attr in ("CineRate", "RecommendedDisplayFrameRate"):
        val = getattr(ds, attr, None)
        if val:
            try:
                fps = float(val)
                if fps > 0:
                    return fps, False
            except (TypeError, ValueError):
                pass

    frame_time_ms = getattr(ds, "FrameTime", None)
    if frame_time_ms:
        try:
            ms = float(frame_time_ms)
            if ms > 0:
                return round(1000.0 / ms, 2), False
        except (TypeError, ValueError):
            pass

    return DEFAULT_FPS, True


def extract_video(ds: pydicom.Dataset, output_path: str) -> Optional[dict]:
    """
    Intenta extraer un MP4 reproducible del cine-loop.

    Devuelve {"frame_count": int, "fps_is_estimated": bool} si tuvo éxito,
    o None si no se pudo (el caller debe conservar únicamente la imagen de
    preview en ese caso — no queda ningún archivo de video a medias).
    """
    transfer_syntax = str(getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", ""))

    try:
        if transfer_syntax in _VIDEO_TRANSFER_SYNTAXES:
            return _remux_encapsulated_video(ds, output_path)
        return _encode_from_pixel_array(ds, output_path)
    except FileNotFoundError:
        logger.warning("ffmpeg no está instalado en este equipo — no se puede extraer el cine-loop (ver setup_jetson.sh).")
        return None
    except Exception as exc:
        logger.warning(f"No se pudo extraer video del cine-loop: {exc}")
        return None


def _run_ffmpeg(cmd: list[str], input_bytes: Optional[bytes] = None) -> bool:
    proc = subprocess.run(cmd, input=input_bytes, capture_output=True, timeout=FFMPEG_TIMEOUT_SECONDS)
    if proc.returncode != 0:
        logger.warning(f"ffmpeg falló ({proc.returncode}): {proc.stderr.decode(errors='ignore')[:500]}")
        return False
    return True


def _remux_encapsulated_video(ds: pydicom.Dataset, output_path: str) -> Optional[dict]:
    """
    El pixel data ya es un stream MPEG/H.264 válido — solo hace falta
    empaquetarlo en un contenedor MP4 reproducible por el navegador, sin
    recodificar (rápido y sin pérdida adicional).
    """
    from pydicom.encaps import generate_pixel_data_frame

    num_frames = int(getattr(ds, "NumberOfFrames", 1) or 1)
    raw = b"".join(generate_pixel_data_frame(ds.PixelData, num_frames))
    if not raw:
        return None

    fps, is_estimated = _estimate_fps(ds)
    with tempfile.NamedTemporaryFile(suffix=".mpg", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name

    try:
        cmd = ["ffmpeg", "-y", "-i", tmp_path, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), output_path]
        if not _run_ffmpeg(cmd) or not os.path.exists(output_path):
            return None
        return {"frame_count": num_frames, "fps_is_estimated": is_estimated}
    finally:
        os.remove(tmp_path)


def _encode_from_pixel_array(ds: pydicom.Dataset, output_path: str) -> Optional[dict]:
    """
    Multi-frame sin comprimir o JPEG-por-frame (el caso más común de
    ecografía): decodifica vía pydicom (requiere pylibjpeg instalado para
    transfer syntaxes JPEG/JPEG2000) y codifica un MP4 real frame a frame.
    """
    frames = ds.pixel_array
    if frames.ndim < 3:
        return None  # no es realmente multi-frame

    n_frames, h, w = frames.shape[0], frames.shape[1], frames.shape[2]
    is_color = frames.ndim == 4 and frames.shape[3] == 3
    pix_fmt_in = "rgb24" if is_color else "gray"

    fps, is_estimated = _estimate_fps(ds)

    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", pix_fmt_in, "-s", f"{w}x{h}", "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        output_path,
    ]
    if not _run_ffmpeg(cmd, input_bytes=frames.astype(np.uint8).tobytes()) or not os.path.exists(output_path):
        return None

    return {"frame_count": n_frames, "fps_is_estimated": is_estimated}
