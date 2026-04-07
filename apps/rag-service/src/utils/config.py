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
    llm_api_key: str
    llm_base_url: str | None
    llm_model: str
    llm_timeout_sec: float
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

    return Settings(
        service_name="rag-service",
        storage_path=storage_path,
        default_top_k=max(1, min(int(top_k_raw), 20)),
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_base_url=os.getenv("LLM_BASE_URL", "").strip() or None,
        llm_model=os.getenv("LLM_MODEL", "").strip(),
        llm_timeout_sec=max(1.0, float(timeout_raw)),
        storage_backend=storage_backend,
        database_url=os.getenv("RAG_DATABASE_URL", "").strip() or None,
    )
