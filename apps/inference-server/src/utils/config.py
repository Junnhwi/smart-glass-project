import os


class Settings:
    celery_broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    storage_region = os.getenv("STORAGE_REGION", os.getenv("AWS_REGION", "ap-northeast-2"))
    # Ollama Cloud / external VLM provider settings
    ollama_api_url = os.getenv(
        "OLLAMA_API_URL",
        os.getenv("API_LLM_OLLAMA_BASE_URL", "https://ollama.example.com"),
    )
    ollama_api_key = os.getenv(
        "OLLAMA_API_KEY",
        os.getenv("API_LLM_OLLAMA_API_KEY", None),
    )
    ollama_timeout_sec = int(
        os.getenv("OLLAMA_TIMEOUT_SEC", os.getenv("API_LLM_OLLAMA_TIMEOUT_SEC", "30"))
    )
    ollama_retry_count = int(os.getenv("OLLAMA_RETRY_COUNT", "1"))
    ollama_vlm_model = os.getenv("OLLAMA_VLM_MODEL", "gemma3:12b")
