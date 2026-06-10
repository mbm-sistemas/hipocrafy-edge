from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from services.sync_service import sync_service
from services.rag_service import rag_service
import logging
import sqlite3
import os
import json
import base64

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/sync", tags=["Deferred Sync"])

# Reference to the local SQLite DB for fallback/pending syncs
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "edge_data.db")

class PullRequest(BaseModel):
    patient_id: str

async def background_push_task():
    """Background task to push pending local studies/transcriptions to the cloud."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            pending_items = conn.execute("SELECT * FROM local_studies WHERE sync_status = 'pending'").fetchall()
            
        for item in pending_items:
            data = dict(item)
            logger.info(f"Attempting to push study {data['study_instance_uid']}...")
            
            # Format findings payload
            try:
                findings = json.loads(data["ai_findings"])
            except Exception:
                findings = {"error": "Failed to decode local findings"}

            # Load image and convert to base64 if present
            image_base64 = None
            if data.get("image_path"):
                # Database stores relative path, like static/previews/...
                # Let's resolve it relative to the workspace root directory (which is where DB_PATH parent dir is)
                parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                full_image_path = os.path.join(parent_dir, data["image_path"])
                if os.path.exists(full_image_path):
                    try:
                        with open(full_image_path, "rb") as image_file:
                            image_base64 = base64.b64encode(image_file.read()).decode('utf-8')
                    except Exception as img_err:
                        logger.warning(f"No se pudo leer la imagen para la sincronización diferida: {img_err}")

            payload = {
                "patient_document": data["patient_dni"],
                "study_date": data["created_at"],
                "modality": data["modality"],
                "ai_findings": findings,
                "image_base64": image_base64
            }

            # Push the unencrypted data to the standard studies endpoint
            success = await sync_service.push_data("studies", payload)
            
            if success:
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute("UPDATE local_studies SET sync_status = 'synced' WHERE study_instance_uid = ?", (data['study_instance_uid'],))
                    logger.info(f"Estudio {data['study_instance_uid']} sincronizado exitosamente de forma diferida.")
                    
    except Exception as e:
        logger.error(f"Error in background push task: {e}")

@router.post("/push")
async def trigger_push(background_tasks: BackgroundTasks):
    """Triggers the deferred sync process to push local data to the cloud securely."""
    background_tasks.add_task(background_push_task)
    return {"status": "accepted", "message": "Push sync triggered in the background."}

@router.post("/pull")
async def trigger_pull(request: PullRequest):
    """Pulls patient data securely from the cloud and ingests it into local RAG/ChromaDB."""
    try:
        # Pull encrypted data specifically for this patient
        decrypted_data = await sync_service.pull_encrypted_data(f"sync/provide/{request.patient_id}")
        
        if not decrypted_data:
            return {"status": "error", "message": "Failed to pull data or no data available."}
            
        # Ingest the decrypted clinical history into the local RAG context
        documents = decrypted_data.get("clinical_history_texts", [])
        if documents:
            rag_service.ingest_patient_data(request.patient_id, documents)
            return {"status": "success", "message": f"Pulled and ingested {len(documents)} context fragments."}
        else:
            return {"status": "success", "message": "Data pulled but no text context found for ingestion."}
            
    except Exception as e:
        logger.error(f"Error in pull sync task: {e}")
        raise HTTPException(status_code=500, detail=str(e))
