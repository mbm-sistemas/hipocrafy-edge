import logging
from core.config import config

logger = logging.getLogger("LLMService")

try:
    # Soporte para versiones nuevas de LangChain (0.2.x+)
    from langchain_ollama import ChatOllama
    LLM_AVAILABLE = True
except ImportError:
    try:
        # Fallback para versiones antiguas
        from langchain_community.chat_models import ChatOllama
        LLM_AVAILABLE = True
    except ImportError as e:
        logger.warning(f"Error importando ChatOllama: {e}. LLMService estara deshabilitado.")
        ChatOllama = None
        LLM_AVAILABLE = False

class LLMService:
    def __init__(self):
        if not LLM_AVAILABLE:
            self.llm = None
            return
            
        # We initialize the ChatOllama wrapper for LangChain
        try:
            self.llm = ChatOllama(
                base_url=config.OLLAMA_BASE_URL,
                model=config.LLM_MODEL,
                temperature=0.0,  # Medical contexts require deterministic responses
                keep_alive=0,
                num_gpu=0
            )
        except TypeError:
            # Fallback if the installed version of ChatOllama does not accept keep_alive/num_gpu directly
            self.llm = ChatOllama(
                base_url=config.OLLAMA_BASE_URL,
                model=config.LLM_MODEL,
                temperature=0.0,
                model_kwargs={"keep_alive": 0, "num_gpu": 0}
            )

    def generate_response(self, prompt: str) -> str:
        """Simple direct generation without RAG context."""
        if not self.llm:
            return "Error: Servicio LLM deshabilitado por falta de dependencias."
        response = self.llm.invoke(prompt)
        return response.content

llm_service = LLMService()
