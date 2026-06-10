try:
    try:
        from langchain_ollama import ChatOllama
    except ImportError:
        from langchain_community.chat_models import ChatOllama

    llm = ChatOllama(
        base_url="http://localhost:11434",
        model="llama3:8b",
        keep_alive=0,
        num_gpu=0
    )
    print("Initializing ChatOllama with keep_alive=0 and num_gpu=0 direct parameter...")
    res = llm.invoke("Di la palabra OK si lees esto.")
    print("Response from ChatOllama:", res.content)
except Exception as e:
    print("Failed to run ChatOllama with direct num_gpu=0:", e)
