from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

CAPTURE_OBJECT_KEY_PREFIX = "captures"

_SAFE_SEGMENT_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")
_REPEATED_SLASH_PATTERN = re.compile(r"/+")


def _normalize_text(value: object | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def sanitize_object_key_segment(value: object | None, fallback: str) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        return fallback
    cleaned = _SAFE_SEGMENT_PATTERN.sub("-", normalized)
    cleaned = cleaned.strip("._-")
    return cleaned or fallback


def _date_path(captured_at: str) -> str:
    candidate = _normalize_text(captured_at).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        parsed = datetime.now(timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y/%m/%d")


def build_capture_object_key(
    *,
    user_id: str,
    captured_at: str,
    capture_id: str,
    file_name: str,
) -> str:
    safe_user_id = sanitize_object_key_segment(user_id, "user")
    safe_capture_id = sanitize_object_key_segment(capture_id, "capture")
    safe_file_name = sanitize_object_key_segment(file_name, "capture.jpg")
    return (
        f"{CAPTURE_OBJECT_KEY_PREFIX}/{safe_user_id}/{_date_path(captured_at)}/"
        f"{safe_capture_id}-{safe_file_name}"
    )


def normalize_capture_object_key_for_user(
    value: object | None,
    *,
    user_id: str,
) -> str:
    normalized = normalize_storage_object_key(value)
    safe_user_id = sanitize_object_key_segment(user_id, "user")
    expected_prefix = f"{CAPTURE_OBJECT_KEY_PREFIX}/{safe_user_id}/"
    if not normalized.startswith(expected_prefix):
        raise ValueError(
            "imageKey must be under the requesting user's captures prefix"
        )
    return normalized


def normalize_storage_object_key(value: object | None) -> str:
    raw_text = "" if value is None else str(value).strip()
    if not raw_text:
        raise ValueError("imageKey must not be blank")
    if any(ord(char) < 32 or ord(char) == 127 for char in raw_text):
        raise ValueError("imageKey must not contain control characters")

    raw_value = _normalize_text(raw_text)
    parsed = urlsplit(raw_value)
    if parsed.scheme or parsed.netloc:
        raise ValueError("imageKey must be a relative object key, not a URL")

    normalized = raw_value.replace("\\", "/")
    if normalized.startswith("/"):
        raise ValueError("imageKey must be a relative object key")

    normalized = _REPEATED_SLASH_PATTERN.sub("/", normalized).strip("/")
    parts = normalized.split("/")
    if not normalized or not parts or any(part in {".", ".."} for part in parts):
        raise ValueError("imageKey must not contain path traversal segments")

    return normalized


def object_key_file_name(value: object | None) -> str | None:
    normalized = normalize_storage_object_key(value)
    return normalized.rsplit("/", 1)[-1] or None
