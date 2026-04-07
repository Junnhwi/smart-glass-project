from datetime import datetime, timezone
from typing import Any, Dict, Tuple

from src.health.checks import (
    check_model_config as _check_model_config,
    check_queue as _check_queue,
    check_storage_config as _check_storage_config,
)


def build_liveness_payload() -> Tuple[int, Dict[str, Any]]:
    return 200, {
        "status": "ok",
        "service": "inference-server",
        "check_type": "liveness",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "api": {"status": "ok"},
        },
    }

def build_health_payload() -> Tuple[int, Dict[str, Any]]:
    queue_status, queue_detail = _check_queue()
    storage_status, storage_detail = _check_storage_config()
    model_status, model_detail = _check_model_config()

    checks = {
        "api": {"status": "ok"},
        "queue": queue_detail,
        "storage": storage_detail,
        "model": model_detail,
    }
    overall_status = (
        "ok"
        if all(status == "ok" for status in (queue_status, storage_status, model_status))
        else "degraded"
    )
    status_code = 200 if overall_status == "ok" else 503

    payload = {
        "status": overall_status,
        "service": "inference-server",
        "check_type": "readiness",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
    return status_code, payload
