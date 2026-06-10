import os
from core.config import config
from services.llm_service import llm_service
import logging

logger = logging.getLogger("RAGService")

try:
    from langchain_community.vectorstores import Chroma
    from langchain_community.embeddings import OllamaEmbeddings
    from langchain_classic.chains import create_retrieval_chain
    from langchain_classic.chains.combine_documents import create_stuff_documents_chain
    from langchain_core.prompts import ChatPromptTemplate
    LANGCHAIN_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Error importando langchain: {e}. RAGService estara deshabilitado.")
    LANGCHAIN_AVAILABLE = False

# Path to local persistent DB for Chroma
CHROMA_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "chromadb")

class RAGService:
    def __init__(self):
        os.makedirs(CHROMA_DB_DIR, exist_ok=True)
        if not LANGCHAIN_AVAILABLE:
            self.embeddings = None
            self.vector_store = None
            self.qa_chain = None
            return
            
        # Using Ollama's local embeddings engine (e.g. nomic-embed-text)
        try:
            self.embeddings = OllamaEmbeddings(
                base_url=config.OLLAMA_BASE_URL,
                model=config.EMBEDDING_MODEL,
                model_kwargs={"keep_alive": 0, "num_gpu": 0}
            )
        except Exception as e:
            logger.warning(f"Error inicializando OllamaEmbeddings con keep_alive: {e}. Reintentando sin keep_alive...")
            self.embeddings = OllamaEmbeddings(
                base_url=config.OLLAMA_BASE_URL,
                model=config.EMBEDDING_MODEL
            )
        
        self.vector_store = Chroma(
            collection_name="patient_clinical_history",
            embedding_function=self.embeddings,
            persist_directory=CHROMA_DB_DIR
        )

        # Setup the QA Prompt
        system_prompt = (
            "Eres un asistente médico inteligente corriendo en un entorno local seguro (Edge). "
            "Usa el siguiente contexto recuperado del historial clínico del paciente para responder la pregunta. "
            "Si no sabes la respuesta o no está en el contexto, indica que no tienes esa información. "
            "No inventes datos médicos. "
            "\n\n"
            "Contexto: {context}"
        )
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}"),
        ])

        self.qa_chain = create_stuff_documents_chain(llm_service.llm, self.prompt)

    def ingest_patient_data(self, patient_id: str, documents: list[str], metadatas: list[dict] = None):
        """Adds text documents to the ChromaDB, associated with a specific patient, clearing old ones first."""
        if not self.vector_store:
            return
            
        try:
            # Delete existing records for this patient to avoid duplicate context
            self.vector_store.delete(where={"patient_id": patient_id})
            logger.info(f"Limpieza de historial previo en RAG para DNI {patient_id} exitosa.")
        except Exception as e:
            logger.warning(f"No se pudo limpiar el historial previo del RAG para DNI {patient_id}: {e}")

        if metadatas is None:
            metadatas = [{"patient_id": patient_id} for _ in documents]
        else:
            for m in metadatas:
                m["patient_id"] = patient_id
                
        self.vector_store.add_texts(texts=documents, metadatas=metadatas)

    def query_patient_context(self, patient_id: str, query: str) -> str:
        """Retrieves context specific to a patient and answers a query."""
        # Filter vector store by patient_id
        retriever = self.vector_store.as_retriever(
            search_kwargs={"filter": {"patient_id": patient_id}, "k": 4}
        )
        
        retrieval_chain = create_retrieval_chain(retriever, self.qa_chain)
        
        response = retrieval_chain.invoke({"input": query})
        return response["answer"]

rag_service = RAGService()
