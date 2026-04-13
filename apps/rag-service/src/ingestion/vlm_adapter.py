from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.api.schemas import MemoryLocationPayload, MemoryRecordPayload


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _dedupe_strings(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []

    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _normalize_text(value)
        if not text or text in seen:
            continue
        deduped.append(text)
        seen.add(text)
    return deduped


def _normalize_structured_objects(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        name = _normalize_text(item.get("name"))
        if not name:
            continue
        visual_features = item.get("visual_features")
        brand = None
        if isinstance(visual_features, dict):
            brand = _normalize_text(visual_features.get("brand")) or None
        nearby_objects = _dedupe_strings(
            item.get("nearby_objects") or item.get("nearby") or []
        )
        normalized.append(
            {
                "name": name,
                "nearby_objects": nearby_objects,
                "visual_features": {"brand": brand},
            }
        )
    return normalized


def _build_tags(
    metadata: Mapping[str, Any], structured_objects: list[dict[str, Any]]
) -> list[str]:
    candidates: list[str] = []
    candidates.extend(_dedupe_strings(metadata.get("tags") or []))
    candidates.extend(_dedupe_strings(metadata.get("detectedObjects") or []))
    candidates.extend(item["name"] for item in structured_objects if item.get("name"))

    for item in structured_objects:
        candidates.extend(item.get("nearby_objects") or [])
        brand = item.get("visual_features", {}).get("brand")
        if brand:
            candidates.append(brand)

    tags: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        text = _normalize_text(candidate)
        if not text or text in seen:
            continue
        tags.append(text)
        seen.add(text)
    return tags


def _resolve_capabilities(result: Mapping[str, Any]) -> dict[str, bool] | None:
    provider_metadata = result.get("providerMetadata")
    if not isinstance(provider_metadata, Mapping):
        return None

    raw_capabilities = provider_metadata.get("capabilities")
    if not isinstance(raw_capabilities, Mapping):
        return None

    return {
        "detectedObjects": bool(raw_capabilities.get("detectedObjects", True)),
        "tags": bool(raw_capabilities.get("tags", True)),
        "positionHint": bool(raw_capabilities.get("positionHint", True)),
        "sceneSummary": bool(raw_capabilities.get("sceneSummary", False)),
        "ocrText": bool(raw_capabilities.get("ocrText", False)),
        "location": bool(raw_capabilities.get("location", False)),
    }


def _build_location_payload(
    metadata: Mapping[str, Any],
    pipeline_output: Mapping[str, Any],
    capabilities: Mapping[str, bool] | None = None,
) -> MemoryLocationPayload:
    if capabilities is not None and not capabilities.get("location"):
        return MemoryLocationPayload()

    location = metadata.get("location")
    if isinstance(location, Mapping):
        payload = MemoryLocationPayload(
            name=_normalize_text(location.get("name")) or None,
            address=_normalize_text(location.get("address")) or None,
            latitude=location.get("latitude"),
            longitude=location.get("longitude"),
        )
        if any([payload.name, payload.address, payload.latitude, payload.longitude]):
            return payload

    location_context = _normalize_text(pipeline_output.get("location_context"))
    if location_context and (capabilities is None or capabilities.get("location")):
        return MemoryLocationPayload(name=location_context)
    return MemoryLocationPayload()


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
    pipeline_output = result.get("pipelineOutput") or {}
    capabilities = _resolve_capabilities(result)

    if capabilities is None:
        structured_objects = _normalize_structured_objects(
            pipeline_output.get("objects") or []
        )

        detected_objects = _dedupe_strings(metadata.get("detectedObjects") or [])
        if not detected_objects and structured_objects:
            detected_objects = [
                item["name"] for item in structured_objects if item.get("name")
            ]

        tags = _build_tags(metadata, structured_objects)

        scene_summary = (
            _normalize_text(metadata.get("sceneSummary"))
            or _normalize_text(pipeline_output.get("scene_summary"))
            or _normalize_text(metadata.get("caption"))
            or None
        )
        ocr_text = (
            _normalize_text(metadata.get("ocrText"))
            or _normalize_text(pipeline_output.get("ocr_text"))
            or None
        )
        position_hint = (
            _normalize_text(metadata.get("positionHint"))
            or _normalize_text(pipeline_output.get("location_context"))
            or None
        )
        location = _build_location_payload(metadata, pipeline_output)
    else:
        detected_objects = (
            _dedupe_strings(metadata.get("detectedObjects") or [])
            if capabilities["detectedObjects"]
            else []
        )
        tags = (
            _dedupe_strings(metadata.get("tags") or [])
            if capabilities["tags"]
            else []
        )
        scene_summary = (
            _normalize_text(metadata.get("sceneSummary"))
            if capabilities["sceneSummary"]
            else None
        ) or None
        ocr_text = (
            _normalize_text(metadata.get("ocrText"))
            if capabilities["ocrText"]
            else None
        ) or None
        position_hint = (
            _normalize_text(metadata.get("positionHint"))
            if capabilities["positionHint"]
            else None
        ) or None
        location = _build_location_payload(metadata, pipeline_output, capabilities)

    return MemoryRecordPayload(
        memory_id=memory_id,
        user_id=user_id,
        image_key=source_image.get("imageKey"),
        image_url=source_image.get("imageUrl"),
        captured_at=result.get("capturedAt"),
        caption=_normalize_text(metadata.get("caption")) or None,
        scene_summary=scene_summary,
        detected_objects=detected_objects,
        tags=tags,
        ocr_text=ocr_text,
        note=None,
        position_hint=position_hint,
        location=location,
    )
