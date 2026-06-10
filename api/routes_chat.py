from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from services.rag_service import rag_service
from services.llm_service import llm_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai", tags=["AI Chat & RAG"])

class ChatRequest(BaseModel):
    patient_id: str
    message: str
    use_rag: bool = True

class IngestRequest(BaseModel):
    patient_id: str
    documents: List[str]
    metadatas: Optional[List[dict]] = None

@router.post("/chat")
async def chat_with_patient_context(request: ChatRequest):
    """Answers a medical question using local RAG context or direct LLM."""
    try:
        if request.use_rag:
            answer = rag_service.query_patient_context(request.patient_id, request.message)
        else:
            answer = llm_service.generate_response(request.message)
            
        return {"answer": answer}
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/context/ingest")
async def ingest_patient_context(request: IngestRequest):
    """Ingests medical documents into the local ChromaDB vector store for RAG."""
    try:
        rag_service.ingest_patient_data(
            patient_id=request.patient_id, 
            documents=request.documents, 
            metadatas=request.metadatas
        )
        return {"status": "success", "message": f"Ingested {len(request.documents)} documents for patient {request.patient_id}"}
    except Exception as e:
        logger.error(f"Error ingesting context: {e}")
        raise HTTPException(status_code=500, detail=str(e))
