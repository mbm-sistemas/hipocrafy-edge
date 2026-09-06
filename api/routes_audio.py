import os
import shutil
import uuid
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from services.whisper_service import whisper_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/audio", tags=["Audio Transcription"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "temp_audio")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribes an uploaded audio file using Whisper locally."""
    # .webm es el formato que produce MediaRecorder en el navegador (grabación
    # desde el consultorio) - sin esto, todo dictado grabado desde la UI web
    # era rechazado con 400 antes de llegar a Whisper.
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ('.wav', '.mp3', '.m4a', '.ogg', '.webm', '.mp4'):
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload wav, mp3, m4a, ogg, webm or mp4.")

    # Nombre generado server-side: el nombre que manda el navegador es siempre
    # "recording.webm" (ver InvoxRecorder/LocalDictationButton), asi que usar
    # file.filename tal cual pisaria el archivo temporal de otro medico
    # dictando al mismo tiempo. uuid4 evita colisiones y path traversal.
    temp_file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{suffix}")

    try:
        # Save the file temporarily
        with open(temp_file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        logger.info(f"Transcribing audio file: {file.filename}")
        transcript = whisper_service.transcribe_audio(temp_file_path)
        
        return {"text": transcript}
    except Exception as e:
        logger.error(f"Error during transcription: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
