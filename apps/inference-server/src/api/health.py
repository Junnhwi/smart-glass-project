import os
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import redis

from src.models.captioning import get_caption_model_spec


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


def _check_queue() -> Tuple[str, Dict[str, Any]]:
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    detail: Dict[str, Any] = {"broker_url": broker_url}

    try:
        client = redis.Redis.from_url(broker_url, socket_connect_timeout=1, socket_timeout=1)
        client.ping()
        detail["status"] = "ok"
    except Exception as exc:
        detail["status"] = "error"
        detail["message"] = str(exc)

    return detail["status"], detail


def _check_storage_config() -> Tuple[str, Dict[str, Any]]:
    region = os.getenv("AWS_REGION", "ap-northeast-2").strip() or "ap-northeast-2"
    bucket_name = os.getenv("AWS_S3_BUCKET_NAME", "").strip()
    missing = [
        name
        for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_S3_BUCKET_NAME")
        if not os.getenv(name, "").strip()
    ]

    detail: Dict[str, Any] = {
        "region": region,
        "bucket_name": bucket_name or None,
    }
    if missing:
        detail["status"] = "error"
        detail["missing_env"] = missing
    else:
        detail["status"] = "ok"

    return detail["status"], detail


def _check_model_config() -> Tuple[str, Dict[str, Any]]:
    model_key = os.getenv("VISION_CAPTION_MODEL", "blip-base").strip() or "blip-base"
    quantization = (
        os.getenv("VISION_CAPTION_QUANTIZATION", "none").strip() or "none"
    )
    dtype_name = os.getenv("VISION_CAPTION_DTYPE", "float16").strip() or "float16"

    detail: Dict[str, Any] = {
        "model_key": model_key,
        "quantization": quantization,
        "dtype": dtype_name,
    }

    errors = []
    try:
        spec = get_caption_model_spec(model_key)
        detail["model_id"] = spec.model_id
    except Exception as exc:
        errors.append(str(exc))

    if quantization not in {"none", "8bit", "4bit"}:
        errors.append("Unsupported quantization")
    if dtype_name not in {"float16", "bfloat16", "float32"}:
        errors.append("Unsupported dtype")

    if errors:
        detail["status"] = "error"
        detail["errors"] = errors
    else:
        detail["status"] = "ok"

    return detail["status"], detail


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
