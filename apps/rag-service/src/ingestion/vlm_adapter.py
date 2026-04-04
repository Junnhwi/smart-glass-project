from typing import Any, Mapping

from src.api.schemas import MemoryLocationPayload, MemoryRecordPayload


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

    return MemoryRecordPayload(
        memory_id=memory_id,
        user_id=user_id,
        image_key=source_image.get("imageKey"),
        image_url=source_image.get("imageUrl"),
        captured_at=result.get("capturedAt"),
        caption=metadata.get("caption"),
        scene_summary=None,
        detected_objects=list(metadata.get("detectedObjects") or []),
        tags=list(metadata.get("tags") or []),
        ocr_text=None,
        note=None,
        position_hint=metadata.get("positionHint"),
        location=MemoryLocationPayload(),
    )
