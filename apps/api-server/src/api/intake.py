from __future__ import annotations

import mimetypes
import os
from datetime import datetime, timezone
from uuid import uuid4

from src.api.schemas import (
    CaptureDispatchPlan,
    CaptureSourceImagePayload,
    CaptureSourceImageSnapshot,
    CaptureUploadRequest,
    CaptureUploadResponse,
    VlmGenerationConfigPayload,
    VlmInferenceRequestPayload,
    VlmSourceImagePayload,
)
from src.modules.media.object_keys import (
    build_capture_object_key,
    normalize_capture_object_key_for_user,
    object_key_file_name,
)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split())
    return normalized or None


def _ensure_identifier(prefix: str, explicit: str | None) -> str:
    normalized = _normalize_text(explicit)
    if normalized:
        return normalized
    return f"{prefix}-{uuid4().hex[:12]}"


def _capture_timestamp(captured_at: str | None) -> str:
    normalized = _normalize_text(captured_at)
    if not normalized:
        return _utc_now_isoformat()

    candidate = normalized.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise ValueError("capturedAt must be a valid ISO 8601 timestamp") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return (
        parsed.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _utc_now_isoformat() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _guess_content_type(file_name: str | None, explicit: str | None) -> str | None:
    normalized = _normalize_text(explicit)
    if normalized:
        return normalized

    normalized_name = _normalize_text(file_name)
    if normalized_name:
        guessed, _ = mimetypes.guess_type(normalized_name)
        if guessed:
            return guessed

    return "image/jpeg"


def _resolve_source_image(payload: CaptureUploadRequest, capture_id: str, captured_at: str) -> CaptureSourceImageSnapshot:
    source_image = payload.sourceImage or CaptureSourceImagePayload()
    explicit_image_key = _normalize_text(source_image.imageKey) or _normalize_text(payload.imageKey)
    normalized_image_key = (
        normalize_capture_object_key_for_user(
            explicit_image_key,
            user_id=payload.userId,
        )
        if explicit_image_key
        else None
    )
    explicit_image_url = _normalize_text(source_image.imageUrl) or _normalize_text(payload.imageUrl)
    explicit_content_type = _normalize_text(source_image.contentType) or _normalize_text(payload.contentType)

    file_name = _normalize_text(payload.fileName)
    if not file_name and normalized_image_key:
        file_name = object_key_file_name(normalized_image_key)

    if not file_name:
        file_name = "capture.jpg"

    if normalized_image_key:
        image_key = normalized_image_key
    else:
        image_key = build_capture_object_key(
            user_id=payload.userId,
            captured_at=captured_at,
            capture_id=capture_id,
            file_name=file_name,
        )

    content_type = _guess_content_type(file_name, explicit_content_type)
    return CaptureSourceImageSnapshot(
        imageKey=image_key,
        imageUrl=explicit_image_url,
        contentType=content_type,
        fileName=file_name,
    )


def build_capture_upload_response(
    payload: CaptureUploadRequest,
) -> CaptureUploadResponse:
    capture_id = _ensure_identifier("capture", payload.captureId)
    request_id = _ensure_identifier("req", payload.requestId)
    memory_id = _ensure_identifier("mem", payload.memoryId)
    captured_at = _capture_timestamp(payload.capturedAt)
    source_image = _resolve_source_image(payload, capture_id, captured_at)

    inference_request = VlmInferenceRequestPayload(
        requestId=request_id,
        taskType=payload.taskType,
        memoryId=memory_id,
        userId=payload.userId,
        capturedAt=captured_at,
        sourceImage=VlmSourceImagePayload(
            imageKey=source_image.imageKey,
            imageUrl=source_image.imageUrl,
            contentType=source_image.contentType,
        ),
        generation=VlmGenerationConfigPayload(**payload.generation.dict())
        if payload.generation
        else None,
    )

    broker_url = _normalize_text(os.getenv("CELERY_BROKER_URL")) or "redis://redis:6379/0"

    return CaptureUploadResponse(
        captureId=capture_id,
        requestId=request_id,
        memoryId=memory_id,
        userId=payload.userId,
        taskType=payload.taskType,
        capturedAt=captured_at,
        sourceImage=source_image,
        inferenceRequest=inference_request,
        dispatch=CaptureDispatchPlan(
            brokerUrl=broker_url,
            note=(
                "Upload registered and worker payload prepared for dispatch."
            ),
        ),
    )


def build_worker_task_kwargs(
    response: CaptureUploadResponse,
    *,
    enqueued_at: str | None = None,
) -> dict[str, object]:
    return {
        "image_key": response.sourceImage.imageKey,
        "user_id": response.userId,
        "memory_id": response.memoryId,
        "captured_at": response.capturedAt,
        "image_url": response.sourceImage.imageUrl,
        "request_id": response.requestId,
        "task_type": response.taskType,
        "enqueued_at": _normalize_text(enqueued_at) or _utc_now_isoformat(),
    }
