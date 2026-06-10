import httpx
import os

ORTHANC_URL = os.getenv("ORTHANC_URL", "http://localhost:8042")
ORTHANC_USERNAME = os.getenv("ORTHANC_USERNAME", "orthanc")
ORTHANC_PASSWORD = os.getenv("ORTHANC_PASSWORD", "orthanc")

async def fetch_dicom_instances(study_id: str):
    """
    Fetches the list of instances for a given study from Orthanc.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ORTHANC_URL}/studies/{study_id}/instances",
            auth=(ORTHANC_USERNAME, ORTHANC_PASSWORD)
        )
        response.raise_for_status()
        return response.json()

async def download_dicom_instance(instance_id: str):
    """
    Downloads the raw DICOM file for a specific instance.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{ORTHANC_URL}/instances/{instance_id}/file",
            auth=(ORTHANC_USERNAME, ORTHANC_PASSWORD)
        )
        response.raise_for_status()
        return response.content

def run_inference(dicom_bytes: bytes):
    """
    Placeholder for the actual 'iaimagenes' AI model inference.
    In reality, this would load the model (e.g., PyTorch/TensorFlow) and process the image.
    """
    # TODO: Integrar el modelo de iaimagenes real aquí
    print("Ejecutando Inferencia de IA sobre la imagen DICOM...")
    
    # Simulación de resultado
    return {
        "finding": "Normal",
        "confidence": 0.98,
        "anomalies": []
    }
