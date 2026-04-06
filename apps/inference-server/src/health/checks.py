import os
import socket
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Tuple

import redis
from celery import Celery

from src.models.registry import resolve_inference_model
from src.worker_preload import get_preload_status_path


def check_queue() -> Tuple[str, Dict[str, Any]]:
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    detail: Dict[str, Any] = {"broker_url": broker_url}

    try:
        client = redis.Redis.from_url(
            broker_url, socket_connect_timeout=1, socket_timeout=1
        )
        client.ping()
        detail["status"] = "ok"
    except Exception as exc:
        detail["status"] = "error"
        detail["message"] = str(exc)

    return detail["status"], detail


def check_storage_config() -> Tuple[str, Dict[str, Any]]:
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


def check_model_config() -> Tuple[str, Dict[str, Any]]:
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
        spec = resolve_inference_model(model_key)
        detail["model_id"] = spec.model_id
        detail["mode"] = spec.mode
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


def check_model_preload() -> Tuple[str, Dict[str, Any]]:
    path = get_preload_status_path()
    detail: Dict[str, Any] = {"status_path": str(path)}

    if not path.exists():
        detail["status"] = "error"
        detail["message"] = "Preload status file is missing"
        return detail["status"], detail

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        detail["status"] = "error"
        detail["message"] = f"Failed to parse preload status: {exc}"
        return detail["status"], detail

    detail.update(payload)
    if payload.get("status") == "ready":
        detail["status"] = "ok"
        return detail["status"], detail

    detail["status"] = "error"
    if "message" not in detail:
        detail["message"] = "Model preload has not completed successfully"
    return detail["status"], detail


def default_worker_name() -> str:
    return f"celery@{socket.gethostname()}"


def _check_worker_process() -> Tuple[str, Dict[str, Any]]:
    cmdline_path = Path("/proc/1/cmdline")
    detail: Dict[str, Any] = {"pid": 1}

    try:
        os.kill(1, 0)
        detail["pid_alive"] = True
    except Exception as exc:
        detail["status"] = "error"
        detail["pid_alive"] = False
        detail["message"] = str(exc)
        return detail["status"], detail

    try:
        cmdline = cmdline_path.read_text(encoding="utf-8", errors="replace").replace(
            "\x00", " "
        ).strip()
    except Exception as exc:
        detail["status"] = "error"
        detail["message"] = f"Failed to read worker process cmdline: {exc}"
        return detail["status"], detail

    detail["cmdline"] = cmdline
    if "celery" in cmdline and "worker" in cmdline:
        detail["status"] = "ok"
    else:
        detail["status"] = "error"
        detail["message"] = "PID 1 is not a Celery worker process"

    return detail["status"], detail


def check_worker_ping(
    celery_app: Celery | None = None,
    worker_name: str | None = None,
) -> Tuple[str, Dict[str, Any]]:
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    resolved_worker_name = worker_name or default_worker_name()
    detail: Dict[str, Any] = {
        "broker_url": broker_url,
        "worker_name": resolved_worker_name,
    }

    app = celery_app or Celery("inference_worker_healthcheck", broker=broker_url)

    try:
        replies = app.control.ping(destination=[resolved_worker_name], timeout=1.0)
    except Exception as exc:
        detail["status"] = "error"
        detail["message"] = str(exc)
        return detail["status"], detail

    if any(reply.get(resolved_worker_name) == "pong" for reply in replies):
        detail["status"] = "ok"
        return detail["status"], detail

    process_status, process_detail = _check_worker_process()
    detail["fallback_process"] = process_detail
    if process_status == "ok":
        detail["status"] = "ok"
        detail["warning"] = "Celery ping did not respond; falling back to worker process check"
    else:
        detail["status"] = "error"
        detail["message"] = "No ping response from Celery worker"

    return detail["status"], detail


def build_worker_health_payload() -> Tuple[int, Dict[str, Any]]:
    worker_status, worker_detail = check_worker_ping()
    queue_status, queue_detail = check_queue()
    storage_status, storage_detail = check_storage_config()
    model_status, model_detail = check_model_config()
    preload_status, preload_detail = check_model_preload()

    checks = {
        "worker": worker_detail,
        "queue": queue_detail,
        "storage": storage_detail,
        "model": model_detail,
        "preload": preload_detail,
    }
    overall_status = (
        "ok"
        if all(
            status == "ok"
            for status in (
                worker_status,
                queue_status,
                storage_status,
                model_status,
                preload_status,
            )
        )
        else "degraded"
    )
    status_code = 0 if overall_status == "ok" else 1

    payload = {
        "status": overall_status,
        "service": "inference-worker",
        "check_type": "readiness",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
    return status_code, payload
