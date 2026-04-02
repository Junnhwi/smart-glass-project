import json
import logging
import os
from datetime import datetime, timezone
from typing import Any


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "client_ip",
            "user_id",
            "memory_id",
            "query",
            "answer_mode",
        ):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True)


def configure_logging() -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_smart_glass_rag_configured", False):
        return

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)
    root_logger._smart_glass_rag_configured = True  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
