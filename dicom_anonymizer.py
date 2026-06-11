"""
DICOM Anonymizer — Hipocrafy Edge
Implements DICOM PS 3.15 Annex E Basic Application Level Confidentiality Profile
plus pixel-level burn-in text masking for ultrasound images.

Usage:
    from dicom_anonymizer import anonymize_dicom_file, anonymize_pixel_data

    # Anonymize a full DICOM file (tags + pixels)
    result = anonymize_dicom_file("input.dcm", "output_anon.dcm")

    # Anonymize only pixel data (numpy array → numpy array)
    anon_pixels = anonymize_pixel_data(pixels)
"""

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Optional

import numpy as np
import pydicom
from pydicom.uid import generate_uid

logger = logging.getLogger("HipocrafyAnonymizer")

# ─── DICOM Tags to anonymize (DICOM PS 3.15 Annex E, Basic Profile) ──────────
# Format: (group, element): replacement_value  |  None = delete tag
_TAG_RULES: dict[tuple, object] = {
    # Patient identification
    (0x0010, 0x0010): "ANONYMIZED^HIPOCRAFY",   # Patient Name
    (0x0010, 0x0020): None,                      # Patient ID → replaced with hash below
    (0x0010, 0x0030): None,                      # Patient Birth Date → zeroed
    (0x0010, 0x0040): None,                      # Patient Sex (keep blank)
    (0x0010, 0x1010): None,                      # Patient Age
    (0x0010, 0x1030): None,                      # Patient Weight
    (0x0010, 0x21B0): None,                      # Additional Patient History
    (0x0010, 0x4000): None,                      # Patient Comments

    # Study / Referring physician
    (0x0008, 0x0090): "HIPOCRAFY",              # Referring Physician Name
    (0x0008, 0x1048): None,                      # Physician(s) of Record
    (0x0008, 0x1050): None,                      # Performing Physician Name
    (0x0008, 0x1070): None,                      # Operators' Name
    (0x0008, 0x1040): None,                      # Institutional Department Name
    (0x0008, 0x0080): "HIPOCRAFY",              # Institution Name
    (0x0008, 0x0081): None,                      # Institution Address
    (0x0032, 0x1032): None,                      # Requesting Physician
    (0x0032, 0x1060): None,                      # Requested Procedure Description

    # Accession / Study IDs
    (0x0008, 0x0050): None,                      # Accession Number
    (0x0020, 0x4000): None,                      # Image Comments
    (0x0040, 0xA124): None,                      # UID (private)
}

# Tags containing UIDs that must be regenerated (to prevent cross-study linkage)
_UID_TAGS = [
    (0x0020, 0x000D),  # Study Instance UID
    (0x0020, 0x000E),  # Series Instance UID
    (0x0008, 0x0018),  # SOP Instance UID
]

# ─── Pixel-level burn-in detection ────────────────────────────────────────────

def _detect_burn_in_rows(pixels: np.ndarray, bright_threshold: int = 200, min_density: float = 0.005) -> list[tuple[int, int]]:
    """
    Detect horizontal bands of burn-in text in ultrasound images.
    Returns list of (start_row, end_row) regions to mask.

    Strategy: ultrasound background ≈ 0-60 gray; burn-in text ≈ 200-255.
    A row is "burn-in active" if ≥ min_density of its pixels exceed bright_threshold.
    Adjacent active rows are grouped into bands.
    """
    if pixels.ndim == 3:
        gray = pixels.mean(axis=2).astype(np.uint8)
    else:
        gray = pixels.astype(np.uint8)

    h, w = gray.shape
    bright_count = (gray >= bright_threshold).sum(axis=1)
    active = bright_count >= (w * min_density)

    bands = []
    in_band = False
    band_start = 0
    for row_idx, is_active in enumerate(active):
        if is_active and not in_band:
            band_start = row_idx
            in_band = True
        elif not is_active and in_band:
            bands.append((band_start, row_idx))
            in_band = False
    if in_band:
        bands.append((band_start, h))

    # Merge adjacent bands within 5px of each other
    merged = []
    for start, end in bands:
        if merged and start - merged[-1][1] <= 5:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))

    # Only keep bands in top 20% or bottom 20% of image (typical burn-in zones)
    top_limit    = int(h * 0.20)
    bottom_limit = int(h * 0.80)
    return [(s, e) for s, e in merged if s < top_limit or e > bottom_limit]


def anonymize_pixel_data(
    pixels: np.ndarray,
    bright_threshold: int = 200,
    min_density: float = 0.005,
    margin_px: int = 2,
    force_mask_top_pct: float = 0.0,
    force_mask_bottom_pct: float = 0.0,
) -> np.ndarray:
    """
    Mask burn-in text regions in a pixel array.

    Args:
        pixels: numpy array (H, W) or (H, W, 3)
        bright_threshold: pixel value above which a pixel is considered "bright text"
        min_density: fraction of bright pixels per row to flag as burn-in
        margin_px: extra rows to mask around detected bands (tolerance)
        force_mask_top_pct: always mask this % of top rows (0.0 = disabled)
        force_mask_bottom_pct: always mask this % of bottom rows (0.0 = disabled)

    Returns:
        Anonymized pixel array (same shape, burn-in regions zeroed)
    """
    result = pixels.copy()
    h = pixels.shape[0]

    # Auto-detect burn-in bands
    bands = _detect_burn_in_rows(pixels, bright_threshold, min_density)
    for start, end in bands:
        r_start = max(0, start - margin_px)
        r_end   = min(h, end   + margin_px)
        result[r_start:r_end] = 0
        logger.debug(f"Masked burn-in rows {r_start}–{r_end}")

    # Force masking of top/bottom strips if configured
    if force_mask_top_pct > 0:
        top_rows = int(h * force_mask_top_pct)
        result[:top_rows] = 0
    if force_mask_bottom_pct > 0:
        bot_rows = int(h * force_mask_bottom_pct)
        result[h - bot_rows:] = 0

    return result


# ─── Tag-level anonymization ──────────────────────────────────────────────────

def _hash_uid(original: str) -> str:
    """Deterministic pseudo-UID from original: sha256 → decimal → fits DICOM UID format."""
    h = hashlib.sha256(original.encode()).hexdigest()
    numeric = str(int(h[:16], 16))[:16]
    return f"2.25.{numeric}"


def anonymize_tags(ds: pydicom.Dataset, original_patient_id: Optional[str] = None) -> pydicom.Dataset:
    """
    Apply DICOM PS 3.15 Annex E Basic Profile tag anonymization in-place.
    Patient ID is replaced with a deterministic hash of the original.
    """
    for (group, element), replacement in _TAG_RULES.items():
        tag = pydicom.tag.Tag(group, element)
        if tag in ds:
            if replacement is None:
                del ds[tag]
            else:
                ds[tag].value = replacement

    # Deterministic patient ID hash (preserves longitudinal pseudonymity)
    pid_tag = pydicom.tag.Tag(0x0010, 0x0020)
    if original_patient_id:
        ds[pid_tag].value = "HIPOCRAFY-" + hashlib.sha256(original_patient_id.encode()).hexdigest()[:12].upper()
    elif pid_tag in ds:
        ds[pid_tag].value = "HIPOCRAFY-UNKNOWN"

    # Regenerate UIDs (breaks cross-study linkage)
    for group, element in _UID_TAGS:
        tag = pydicom.tag.Tag(group, element)
        if tag in ds:
            original_uid = str(ds[tag].value)
            ds[tag].value = _hash_uid(original_uid)

    # Remove private tags entirely (manufacturer-specific, may contain PHI)
    ds.remove_private_tags()

    return ds


# ─── Full pipeline ─────────────────────────────────────────────────────────────

def anonymize_dicom_dataset(
    ds: pydicom.Dataset,
    anonymize_pixels: bool = True,
    force_mask_top_pct: float = 0.0,
    force_mask_bottom_pct: float = 0.0,
) -> pydicom.Dataset:
    """
    Anonymize a pydicom Dataset in-place (tags + optionally pixels).
    Returns the modified dataset.
    """
    original_pid = None
    pid_tag = pydicom.tag.Tag(0x0010, 0x0020)
    if pid_tag in ds:
        original_pid = str(ds[pid_tag].value)

    # 1. Tag anonymization
    anonymize_tags(ds, original_pid)

    # 2. Pixel anonymization
    if anonymize_pixels:
        try:
            pixels = ds.pixel_array
            anon_pixels = anonymize_pixel_data(
                pixels,
                force_mask_top_pct=force_mask_top_pct,
                force_mask_bottom_pct=force_mask_bottom_pct,
            )
            # Re-encode: for uncompressed transfer syntaxes only
            uncompressed = [
                "1.2.840.10008.1.2",       # Implicit VR Little Endian
                "1.2.840.10008.1.2.1",     # Explicit VR Little Endian
                "1.2.840.10008.1.2.2",     # Explicit VR Big Endian
            ]
            if str(ds.file_meta.TransferSyntaxUID) in uncompressed:
                ds.PixelData = anon_pixels.tobytes()
            else:
                logger.warning("Compressed transfer syntax — pixel anonymization skipped (re-encode not supported).")
        except Exception as exc:
            logger.warning(f"Pixel anonymization skipped: {exc}")

    return ds


def anonymize_dicom_file(
    input_path: str,
    output_path: str,
    anonymize_pixels: bool = True,
    force_mask_top_pct: float = 0.0,
    force_mask_bottom_pct: float = 0.0,
) -> dict:
    """
    Anonymize a DICOM file and save to output_path.
    Returns summary dict with original/anonymized metadata.
    """
    ds = pydicom.dcmread(input_path)

    original_info = {
        "patient_name": str(ds.get("PatientName", "UNKNOWN")),
        "patient_id":   str(ds.get("PatientID",   "UNKNOWN")),
        "study_uid":    str(ds.get("StudyInstanceUID", "")),
    }

    ds = anonymize_dicom_dataset(
        ds,
        anonymize_pixels=anonymize_pixels,
        force_mask_top_pct=force_mask_top_pct,
        force_mask_bottom_pct=force_mask_bottom_pct,
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    pydicom.dcmwrite(output_path, ds)

    logger.info(f"Anonymized DICOM → {output_path}")

    return {
        "input":          input_path,
        "output":         output_path,
        "original_pid":   original_info["patient_id"],
        "original_name":  original_info["patient_name"],
        "original_uid":   original_info["study_uid"],
        "anon_pid":       str(ds.get("PatientID", "")),
        "anon_uid":       str(ds.get("StudyInstanceUID", "")),
    }


def anonymize_orthanc_study(
    study_id: str,
    orthanc_url: str,
    orthanc_auth: tuple,
    output_dir: str,
    anonymize_pixels: bool = True,
) -> list[dict]:
    """
    Download all DICOM instances of an Orthanc study, anonymize, and save to output_dir.
    Returns list of anonymization result dicts.
    """
    import requests as req

    instances_resp = req.get(f"{orthanc_url}/studies/{study_id}/instances", auth=orthanc_auth, timeout=30)
    instances_resp.raise_for_status()
    instance_ids = [inst["ID"] for inst in instances_resp.json()]

    results = []
    for inst_id in instance_ids:
        dicom_resp = req.get(f"{orthanc_url}/instances/{inst_id}/file", auth=orthanc_auth, timeout=30)
        dicom_resp.raise_for_status()

        in_path  = os.path.join(output_dir, f"{inst_id}_original.dcm")
        out_path = os.path.join(output_dir, f"{inst_id}_anon.dcm")

        with open(in_path, "wb") as f:
            f.write(dicom_resp.content)

        result = anonymize_dicom_file(in_path, out_path, anonymize_pixels=anonymize_pixels)
        os.remove(in_path)  # remove unencrypted original
        results.append(result)

    logger.info(f"Anonymized {len(results)} instances for study {study_id}")
    return results


# ─── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys

    parser = argparse.ArgumentParser(description="Hipocrafy DICOM Anonymizer")
    parser.add_argument("input",  help="Input DICOM file")
    parser.add_argument("output", help="Output anonymized DICOM file")
    parser.add_argument("--no-pixels", action="store_true", help="Skip pixel anonymization")
    parser.add_argument("--force-top",    type=float, default=0.0, help="Force-mask top N%% of image (e.g. 0.10)")
    parser.add_argument("--force-bottom", type=float, default=0.0, help="Force-mask bottom N%% of image (e.g. 0.10)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s %(message)s")
    result = anonymize_dicom_file(
        args.input, args.output,
        anonymize_pixels=not args.no_pixels,
        force_mask_top_pct=args.force_top,
        force_mask_bottom_pct=args.force_bottom,
    )
    print(f"\nOriginal:   {result['original_name']} / {result['original_pid']}")
    print(f"Anonymized: {result['anon_pid']}")
    print(f"Output:     {result['output']}\n")
