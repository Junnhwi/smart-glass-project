import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

# 광록님의 성능 측정 필드와 팀원분의 상세 정보 필드가 모두 통합된 리스트입니다!
LOG_EXTRA_FIELDS = (
    "request_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "client_ip",
    "task_name",
    "image_key",
    "memory_id",
    "user_id",
    "model_key",
    "model_id",
    "model_mode",
    "quantization",
    "dtype_name",
    "settings_source",
    "soft_time_limit_sec",
    "hard_time_limit_sec",
    "fallback_model_key",
    "fallback_triggered",
    "latency_sec",
    "load_time_sec",
    "queue_wait_sec",
    "storage_read_sec",
    "image_decode_sec",
    "model_inference_sec",
    "task_latency_sec",
    "peak_memory_mb",
    "retry_count",
    "next_retry_count",
    "max_retries",
    "retry_delay_sec",
    "retry_backoff_multiplier",
    "retry_max_delay_sec",
    "retryable",
    "failure_category",
    "error_code",
)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 팀원분이 정리하신 깔끔한 반복문 구조를 사용합니다
        for key in LOG_EXTRA_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)


def configure_logging() -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_smart_glass_configured", False):
        return

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)
    root_logger._smart_glass_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)