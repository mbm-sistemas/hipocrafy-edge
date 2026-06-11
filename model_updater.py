"""
OTA Model Updater — Hipocrafy Edge
Checks the backend for newer model versions and downloads them to local disk.
Run on startup and periodically (every 6 hours via the scheduler in main.py).
"""

import json
import logging
import os
import pickle
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("HipocrafyOTA")

CLOUD_URL     = os.getenv("HIPOCRAFY_CLOUD_URL", "").rstrip("/")
GATEWAY_TOKEN = os.getenv("GATEWAY_API_TOKEN", "")
MODELS_DIR    = Path(os.getenv("MODELS_DIR", "/home/pmoraga/hipocrafy-edge/models"))
VERSION_FILE  = MODELS_DIR / "versions.json"
TIMEOUT       = 30

SPECIALTIES = ["ginecologia", "obstetricia", "medicina_interna", "general"]


def _gateway_headers() -> dict:
    return {
        "Authorization": f"Bearer {GATEWAY_TOKEN}",
        "Accept": "application/json",
    }


def _api_base() -> str:
    base = CLOUD_URL
    if base.endswith("/api"):
        base = base[:-4]
    return base.rstrip("/") + "/api/edge-gateway"


def load_local_versions() -> dict:
    if VERSION_FILE.exists():
        try:
            return json.loads(VERSION_FILE.read_text())
        except Exception:
            pass
    return {}


def save_local_versions(versions: dict):
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(json.dumps(versions, indent=2))


def _download_file(url: str, dest: Path) -> bool:
    try:
        resp = requests.get(url, headers=_gateway_headers(), timeout=TIMEOUT, stream=True)
        if resp.status_code != 200:
            logger.warning(f"Download failed {url} → HTTP {resp.status_code}")
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"Downloaded → {dest}")
        return True
    except Exception as exc:
        logger.error(f"Download error {url}: {exc}")
        return False


def check_and_update(specialty: str) -> bool:
    """
    Returns True if a new model was downloaded for this specialty.
    Retries up to 3 times on network errors with exponential backoff (2s, 4s, 8s).
    Non-retryable errors (404, auth, bad JSON) fail immediately.
    """
    if not CLOUD_URL or not GATEWAY_TOKEN:
        logger.warning("OTA skipped: HIPOCRAFY_CLOUD_URL or GATEWAY_API_TOKEN not set.")
        return False

    url = f"{_api_base()}/models/latest/{specialty}"
    max_retries = 3
    remote = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, headers=_gateway_headers(), timeout=TIMEOUT)
            if resp.status_code == 404:
                logger.info(f"No model available for specialty={specialty}")
                return False
            if resp.status_code in (401, 403):
                logger.error(f"OTA auth error for {specialty}: HTTP {resp.status_code}")
                return False
            resp.raise_for_status()
            remote = resp.json()
            break
        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            wait = 2 ** attempt  # 2s, 4s, 8s
            if attempt < max_retries:
                logger.warning(
                    f"OTA network error for {specialty} (attempt {attempt}/{max_retries}), "
                    f"retry in {wait}s: {exc}"
                )
                time.sleep(wait)
            else:
                logger.error(f"OTA check failed after {max_retries} attempts for {specialty}: {exc}")
                return False
        except Exception as exc:
            logger.error(f"OTA non-retryable error for {specialty}: {exc}")
            return False

    if remote is None:
        return False

    remote_version = remote.get("version")
    local_versions = load_local_versions()

    if local_versions.get(specialty) == remote_version:
        logger.debug(f"Model {specialty} v{remote_version} already up-to-date.")
        return False

    logger.info(f"New model available: {specialty} v{remote_version} (local={local_versions.get(specialty, 'none')})")

    spec_dir = MODELS_DIR / specialty
    urls = remote.get("download_urls", {})

    downloads = {
        "model":    spec_dir / f"{specialty}_v{remote_version}.onnx",
        "scaler":   spec_dir / f"{specialty}_v{remote_version}_scaler.pkl",
        "features": spec_dir / f"{specialty}_v{remote_version}_features.json",
        "imputer":  spec_dir / f"{specialty}_v{remote_version}_imputer.pkl",
    }

    for key, dest in downloads.items():
        if not _download_file(urls[key], dest):
            logger.error(f"Failed to download {key} for {specialty} v{remote_version} — aborting update.")
            return False

    # Write "latest" symlink files so inference code always reads the same path
    (spec_dir / f"{specialty}_latest.onnx").write_bytes((spec_dir / f"{specialty}_v{remote_version}.onnx").read_bytes())
    (spec_dir / f"{specialty}_latest_scaler.pkl").write_bytes((spec_dir / f"{specialty}_v{remote_version}_scaler.pkl").read_bytes())
    (spec_dir / f"{specialty}_latest_features.json").write_text((spec_dir / f"{specialty}_v{remote_version}_features.json").read_text())
    (spec_dir / f"{specialty}_latest_imputer.pkl").write_bytes((spec_dir / f"{specialty}_v{remote_version}_imputer.pkl").read_bytes())

    local_versions[specialty] = remote_version
    save_local_versions(local_versions)
    logger.info(f"Model {specialty} updated to v{remote_version}")
    return True


def run_ota_check() -> dict:
    """Check all specialties and return summary."""
    results = {}
    for specialty in SPECIALTIES:
        results[specialty] = check_and_update(specialty)
    updated = [s for s, v in results.items() if v]
    if updated:
        logger.info(f"OTA update complete — updated: {updated}")
    else:
        logger.info("OTA check complete — all models up-to-date.")
    return results


# ─── Inference helper ────────────────────────────────────────────────────────

def load_model_bundle(specialty: str):
    """
    Returns (ort_session, scaler, imputer, feature_names) or None if not available.
    Used by analyze_study() to run local structured inference before calling cloud AI.
    """
    try:
        import onnxruntime as ort

        spec_dir = MODELS_DIR / specialty
        onnx_path    = spec_dir / f"{specialty}_latest.onnx"
        scaler_path  = spec_dir / f"{specialty}_latest_scaler.pkl"
        feat_path    = spec_dir / f"{specialty}_latest_features.json"
        imputer_path = spec_dir / f"{specialty}_latest_imputer.pkl"

        if not all(p.exists() for p in [onnx_path, scaler_path, feat_path, imputer_path]):
            return None

        session       = ort.InferenceSession(str(onnx_path))
        scaler        = pickle.loads(scaler_path.read_bytes())
        imputer       = pickle.loads(imputer_path.read_bytes())
        feature_names = json.loads(feat_path.read_text())

        return session, scaler, imputer, feature_names
    except Exception as exc:
        logger.warning(f"Could not load model bundle for {specialty}: {exc}")
        return None


REGIONS = ["NOA", "NEA", "Cuyo", "Pampeana", "Patagonia", "Metropolitana"]


def _build_feature_row(
    organ_analysis: dict,
    feature_names: list[str],
    population_context: dict | None = None,
) -> list[float]:
    """Build a flat feature vector matching feature_names order."""
    import math

    flat: dict[str, float] = {}

    # Organ measurements
    for organ, measurements in organ_analysis.items():
        if not isinstance(measurements, dict):
            continue
        for key, val in measurements.items():
            flat[f"{organ}__{key}"] = float(val) if val is not None else float("nan")

    # Population context (mirrors model_trainer.flatten_population_context)
    if population_context:
        flat["pop__altitude_m"]        = float(population_context.get("altitude_m") or 0)
        flat["pop__patient_age_years"] = float(population_context.get("patient_age_years") or float("nan"))
        flat["pop__patient_bmi"]       = float(population_context.get("patient_bmi") or float("nan"))
        flat["pop__parity"]            = float(population_context.get("parity") or 0)
        region = population_context.get("region") or ""
        for r in REGIONS:
            flat[f"pop__region_{r}"] = 1.0 if region == r else 0.0

    return [flat.get(f, float("nan")) for f in feature_names]


def predict_from_organ_analysis(
    specialty: str,
    organ_analysis: dict,
    population_context: dict | None = None,
) -> dict | None:
    """
    Run local MLP inference on organ_analysis measurements + optional population context.
    Returns {probability, label, model_version, used_population_context} or None.
    """
    import numpy as np

    bundle = load_model_bundle(specialty)
    if bundle is None:
        return None

    session, scaler, imputer, feature_names = bundle

    row = _build_feature_row(organ_analysis, feature_names, population_context)
    X = np.array([row], dtype=np.float32)
    X = imputer.transform(X).astype(np.float32)
    X = scaler.transform(X).astype(np.float32)

    prob = float(session.run(["probability"], {"features": X})[0][0])
    label = "patologico" if prob >= 0.5 else "normal"

    versions = load_local_versions()
    return {
        "probability":             round(prob, 4),
        "label":                   label,
        "model_version":           versions.get(specialty, "unknown"),
        "used_population_context": population_context is not None,
    }
