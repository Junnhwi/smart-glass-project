import os
from dataclasses import dataclass
from pathlib import Path


def _default_storage_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "memory_store.json"


@dataclass(frozen=True, slots=True)
class Settings:
    service_name: str
    storage_path: Path
    default_top_k: int
    llm_provider: str = "auto"
    llm_api_key: str = ""
    llm_base_url: str | None = None
    llm_model: str = ""
    llm_timeout_sec: float = 20.0
    storage_backend: str = "file"
    database_url: str | None = None

    @property
    def llm_enabled(self) -> bool:
        return bool(self.llm_api_key and self.llm_model)


def get_settings() -> Settings:
    storage_raw = os.getenv("RAG_STORAGE_PATH", "").strip()
    storage_path = Path(storage_raw) if storage_raw else _default_storage_path()
    storage_backend = os.getenv("RAG_STORAGE_BACKEND", "file").strip().lower()
    if not storage_backend:
        storage_backend = "file"
    if storage_backend not in {"file", "postgres"}:
        raise ValueError(
            "RAG_STORAGE_BACKEND must be either 'file' or 'postgres'"
        )
    top_k_raw = os.getenv("RAG_DEFAULT_TOP_K", "5").strip() or "5"
    timeout_raw = os.getenv("LLM_TIMEOUT_SEC", "20").strip() or "20"
    llm_provider = os.getenv("LLM_PROVIDER", "auto").strip().lower() or "auto"
    llm_api_key = os.getenv("LLM_API_KEY", "").strip()
    llm_base_url = os.getenv("LLM_BASE_URL", "").strip() or None
    llm_model = os.getenv("LLM_MODEL", "").strip()

    if llm_provider == "ollama":
        llm_api_key = llm_api_key or "ollama"
        llm_base_url = llm_base_url or "http://localhost:11434/v1"
        llm_model = llm_model or "qwen2.5:3b"

    return Settings(
        service_name="rag-service",
        storage_path=storage_path,
        default_top_k=max(1, min(int(top_k_raw), 20)),
        llm_provider=llm_provider,
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        llm_timeout_sec=max(1.0, float(timeout_raw)),
        storage_backend=storage_backend,
        database_url=os.getenv("RAG_DATABASE_URL", "").strip() or None,
    )
