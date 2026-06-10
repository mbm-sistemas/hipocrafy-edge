import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Gateway settings
    GATEWAY_NAME = os.getenv("GATEWAY_NAME", "Nodo Local 01")
    API_TOKEN = os.getenv("GATEWAY_API_TOKEN")
    CLOUD_URL = os.getenv("HIPOCRAFY_CLOUD_URL", "https://qas.hipocrafy-api.mbmsistemas.com.ar/api/edge-gateway")
    
    # Orthanc
    ORTHANC_URL = os.getenv("ORTHANC_URL", "http://localhost:8042")
    ORTHANC_USER = os.getenv("ORTHANC_USER", "orthanc")
    ORTHANC_PASS = os.getenv("ORTHANC_PASS", "orthanc")

    # Security
    ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "0123456789abcdef0123456789abcdef")  # 32 bytes for AES-256

    # AI Models
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    LLM_MODEL = os.getenv("LLM_MODEL", "llama3:8b")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")

config = Config()
