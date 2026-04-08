import os
import re
from typing import Any, Dict
from uuid import uuid4

from src.models.registry import resolve_inference_model


SPATIAL_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\bnext to\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} 옆",
    ),
    (
        re.compile(
            r"\bbeside\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} 옆",
    ),
    (
        re.compile(
            r"\bnear\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} 근처",
    ),
    (
        re.compile(
            r"\binside\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} 안",
    ),
    (
        re.compile(
            r"\bunder\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} 아래",
    ),
    (
        re.compile(
            r"\bon top of\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} 위",
    ),
    (
        re.compile(
            r"\bon\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} 위",
    ),
    (
        re.compile(
            r"\bin\s+(?:the\s+|a\s+|an\s+)?([a-z0-9][a-z0-9\s-]{1,40})",
            re.I,
        ),
        "{obj} 안",
    ),
)

SPATIAL_CONNECTOR_SPLIT = re.compile(
    r"\s+(?:next to|beside|near|inside|under|on top of|on|in)\b",
    re.I,
)


def _normalize_whitespace(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def build_request_id(request_id: str | None = None) -> str:
    normalized = _normalize_whitespace(request_id)
    if normalized:
        return normalized
    return f"vlm-{uuid4().hex}"


def _clean_spatial_object(value: str) -> str:
    cleaned = _normalize_whitespace(value)
    if not cleaned:
        return ""

    cleaned = SPATIAL_CONNECTOR_SPLIT.split(cleaned, maxsplit=1)[0]
    cleaned = re.sub(r"^(?:the|a|an)\s+", "", cleaned, flags=re.I)
    return _normalize_whitespace(cleaned)


def extract_position_hint(caption: str | None) -> str | None:
    cleaned = _normalize_whitespace(caption)
    if not cleaned:
        return None

    for pattern, template in SPATIAL_RULES:
        match = pattern.search(cleaned)
        if not match:
            continue
        target = _clean_spatial_object(match.group(1))
        if target:
            return template.format(obj=target)

    return None


def _include_provider_raw_metadata() -> bool:
    raw_value = os.getenv("VISION_PROVIDER_METADATA_INCLUDE_RAW", "").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _resolve_model_metadata(model_key: str) -> tuple[str | None, str | None, str | None]:
    normalized_key = _normalize_whitespace(model_key) or None
    try:
        spec = resolve_inference_model(model_key)
        return spec.key, spec.model_id, spec.family
    except Exception:
        return normalized_key, normalized_key, None


def build_provider_metadata(
    *,
    model_key: str,
    quantization: str,
    dtype_name: str,
    generation_result: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    generation_result = generation_result or {}
    resolved_key, resolved_model_id, resolved_family = _resolve_model_metadata(model_key)
    provider_metadata: Dict[str, Any] = {
        "modelKey": resolved_key,
        "modelId": resolved_model_id,
        "modelFamily": resolved_family,
        "quantization": quantization,
        "dtype": dtype_name,
        "provider": "huggingface-transformers",
        "capabilities": spec.capabilities.to_contract_payload(),
        "raw": None,
    }

    if _include_provider_raw_metadata():
        provider_metadata["raw"] = {
            "device": generation_result.get("device"),
            "prompt": generation_result.get("prompt"),
        }

    return provider_metadata


def build_vlm_success_result(
    *,
    request_id: str,
    user_id: str,
    image_key: str,
    model_key: str,
    quantization: str,
    dtype_name: str,
    generation_result: Dict[str, Any],
    memory_id: str | None = None,
    image_url: str | None = None,
    captured_at: str | None = None,
    task_type: str = "caption",
    content_type: str | None = None,
    inference_metadata: Dict[str, Any] | None = None,
    pipeline_output: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    caption = _normalize_whitespace(generation_result.get("caption")) or None
    metadata = inference_metadata or {
        "caption": caption,
        "sceneSummary": None,
        "detectedObjects": [],
        "tags": [],
        "ocrText": None,
        "positionHint": extract_position_hint(caption),
        "location": None,
    }
    return {
        "status": "success",
        "requestId": request_id,
        "taskType": task_type,
        "memoryId": _normalize_whitespace(memory_id) or None,
        "userId": _normalize_whitespace(user_id),
        "capturedAt": _normalize_whitespace(captured_at) or None,
        "sourceImage": {
            "imageKey": _normalize_whitespace(image_key) or None,
            "imageUrl": _normalize_whitespace(image_url) or None,
            "contentType": _normalize_whitespace(content_type) or None,
        },
        "metadata": metadata,
        "pipelineOutput": pipeline_output,
        "providerMetadata": build_provider_metadata(
            model_key=model_key,
            quantization=quantization,
            dtype_name=dtype_name,
            generation_result=generation_result,
        ),
        "runtime": {
            "latencySec": generation_result.get("elapsed_sec"),
            "peakMemoryMb": generation_result.get("peak_memory_mb"),
            "loadTimeSec": generation_result.get("load_time_sec"),
        },
    }


def build_vlm_error_result(
    *,
    request_id: str,
    user_id: str,
    image_key: str,
    error: Exception,
    model_key: str,
    quantization: str,
    dtype_name: str,
    memory_id: str | None = None,
    image_url: str | None = None,
    task_type: str = "caption",
    content_type: str | None = None,
) -> Dict[str, Any]:
    error_code = "inference_task_error"
    retryable = not isinstance(error, ValueError)
    return {
        "status": "error",
        "requestId": request_id,
        "taskType": task_type,
        "memoryId": _normalize_whitespace(memory_id) or None,
        "userId": _normalize_whitespace(user_id),
        "sourceImage": {
            "imageKey": _normalize_whitespace(image_key) or None,
            "imageUrl": _normalize_whitespace(image_url) or None,
            "contentType": _normalize_whitespace(content_type) or None,
        },
        "errorCode": error_code,
        "message": str(error),
        "retryable": retryable,
        "providerMetadata": build_provider_metadata(
            model_key=model_key,
            quantization=quantization,
            dtype_name=dtype_name,
        ),
    }
