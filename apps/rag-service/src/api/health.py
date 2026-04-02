from datetime import datetime, timezone
from typing import Any

from src.retriever.service import RagQueryService
from src.utils.config import Settings


def build_liveness_payload() -> tuple[int, dict[str, Any]]:
    return 200, {
        "status": "ok",
        "service": "rag-service",
        "check_type": "liveness",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "api": {"status": "ok"},
        },
    }


def build_health_payload(
    settings: Settings,
    service: RagQueryService,
) -> tuple[int, dict[str, Any]]:
    storage_detail = service.store.readiness_detail()
    llm_detail = {
        "status": "ok",
        "provider": "openai-compatible" if settings.llm_enabled else "template-fallback",
        "model": settings.llm_model or None,
        "base_url": settings.llm_base_url,
    }

    payload = {
        "status": "ok",
        "service": "rag-service",
        "check_type": "readiness",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "api": {"status": "ok"},
            "storage": storage_detail,
            "llm": llm_detail,
        },
    }
    return 200, payload
