import os
import shutil
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
    if not file.filename.endswith(('.wav', '.mp3', '.m4a', '.ogg')):
        raise HTTPException(status_code=400, detail="Unsupported file format. Please upload wav, mp3, m4a, or ogg.")
        
    temp_file_path = os.path.join(UPLOAD_DIR, file.filename)
    
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
