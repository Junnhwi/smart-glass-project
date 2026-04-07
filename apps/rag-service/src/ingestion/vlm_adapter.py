from __future__ import annotations

from typing import Any, Mapping

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
    candidates.extend(
        item["name"] for item in structured_objects if item.get("name")
    )

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


def _build_location_payload(
    metadata: Mapping[str, Any],
    pipeline_output: Mapping[str, Any],
) -> MemoryLocationPayload:
    location = metadata.get("location")
    if isinstance(location, dict):
        payload = MemoryLocationPayload(
            name=_normalize_text(location.get("name")) or None,
            address=_normalize_text(location.get("address")) or None,
            latitude=location.get("latitude"),
            longitude=location.get("longitude"),
        )
        if any([payload.name, payload.address, payload.latitude, payload.longitude]):
            return payload

    location_context = _normalize_text(pipeline_output.get("location_context"))
    if location_context:
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
    structured_objects = _normalize_structured_objects(
        pipeline_output.get("objects") or []
    )

    detected_objects = list(metadata.get("detectedObjects") or [])
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

    return MemoryRecordPayload(
        memory_id=memory_id,
        user_id=user_id,
        image_key=source_image.get("imageKey"),
        image_url=source_image.get("imageUrl"),
        captured_at=result.get("capturedAt"),
        caption=metadata.get("caption"),
        scene_summary=scene_summary,
        detected_objects=detected_objects,
        tags=tags,
        ocr_text=ocr_text,
        note=None,
        position_hint=position_hint,
        location=_build_location_payload(metadata, pipeline_output),
    )
