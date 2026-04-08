from collections.abc import Mapping
from typing import Any

from src.api.schemas import MemoryLocationPayload, MemoryRecordPayload


def _resolve_capabilities(result: Mapping[str, Any]) -> dict[str, bool]:
    provider_metadata = result.get("providerMetadata") or {}
    raw_capabilities = provider_metadata.get("capabilities") or {}
    return {
        "detectedObjects": bool(raw_capabilities.get("detectedObjects", True)),
        "tags": bool(raw_capabilities.get("tags", True)),
        "positionHint": bool(raw_capabilities.get("positionHint", True)),
        "sceneSummary": bool(raw_capabilities.get("sceneSummary", False)),
        "ocrText": bool(raw_capabilities.get("ocrText", False)),
        "location": bool(raw_capabilities.get("location", False)),
    }


def _build_location_payload(
    metadata: Mapping[str, Any], capabilities: Mapping[str, bool]
) -> MemoryLocationPayload:
    if not capabilities.get("location"):
        return MemoryLocationPayload()
    raw_location = metadata.get("location")
    if not isinstance(raw_location, Mapping):
        return MemoryLocationPayload()
    return MemoryLocationPayload(
        name=raw_location.get("name"),
        address=raw_location.get("address"),
        latitude=raw_location.get("latitude"),
        longitude=raw_location.get("longitude"),
    )


def memory_record_from_vlm_result(result: Mapping[str, Any]) -> MemoryRecordPayload:
    status = str(result.get("status", "")).strip().lower()
    if status != "success":
        raise ValueError("Only successful VLM inference results can be indexed")

    memory_id = str(result.get("memoryId") or "").strip()
    user_id = str(result.get("userId") or "").strip()
    if not memory_id or not user_id:
        raise ValueError("memoryId and userId are required for RAG indexing")

    source_image = result.get("sourceImage") or {}
    metadata = result.get("metadata") or {}
    capabilities = _resolve_capabilities(result)

    return MemoryRecordPayload(
        memory_id=memory_id,
        user_id=user_id,
        image_key=source_image.get("imageKey"),
        image_url=source_image.get("imageUrl"),
        captured_at=result.get("capturedAt"),
        caption=metadata.get("caption"),
        scene_summary=metadata.get("sceneSummary")
        if capabilities["sceneSummary"]
        else None,
        detected_objects=list(metadata.get("detectedObjects") or [])
        if capabilities["detectedObjects"]
        else [],
        tags=list(metadata.get("tags") or []) if capabilities["tags"] else [],
        ocr_text=metadata.get("ocrText") if capabilities["ocrText"] else None,
        note=None,
        position_hint=metadata.get("positionHint")
        if capabilities["positionHint"]
        else None,
        location=_build_location_payload(metadata, capabilities),
    )
