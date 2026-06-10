import os
from faster_whisper import WhisperModel
from core.config import config
import logging

logger = logging.getLogger(__name__)

class WhisperService:
    def __init__(self):
        self.model_size = config.WHISPER_MODEL # "small", "base", etc.
        # Check if CUDA is available, otherwise fallback to CPU
        self.device = "cuda" if self._is_cuda_available() else "cpu"
        self.compute_type = "float16" if self.device == "cuda" else "int8"
        
        try:
            logger.info(f"Loading Whisper model '{self.model_size}' on {self.device} with {self.compute_type}")
            self.model = WhisperModel(self.model_size, device=self.device, compute_type=self.compute_type)
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            self.model = None

    def _is_cuda_available(self):
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def transcribe_audio(self, file_path: str) -> str:
        """Transcribes an audio file using faster-whisper."""
        if not self.model:
            return "El modelo de transcripción no está disponible."
            
        try:
            segments, info = self.model.transcribe(file_path, beam_size=5, language="es")
            
            logger.info(f"Detected language '{info.language}' with probability {info.language_probability}")
            
            transcript = []
            for segment in segments:
                transcript.append(segment.text)
                
            return " ".join(transcript).strip()
        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return f"Error transcribiendo audio: {str(e)}"

whisper_service = WhisperService()
