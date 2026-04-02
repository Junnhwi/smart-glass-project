from src.api.schemas import MemoryRecordPayload
from src.ingestion.models import MemoryDocument, MemoryLocation
from src.utils.text import dedupe_strings, extract_spatial_hint, normalize_whitespace


class MemoryIngestionService:
    def normalize_many(self, payloads: list[MemoryRecordPayload]) -> list[MemoryDocument]:
        return [self.normalize(payload) for payload in payloads]

    def normalize(self, payload: MemoryRecordPayload) -> MemoryDocument:
        memory_id = self._require_identifier(payload.memory_id, field_name="memory_id")
        user_id = self._require_identifier(payload.user_id, field_name="user_id")

        location = MemoryLocation(
            name=normalize_whitespace(payload.location.name) or None,
            address=normalize_whitespace(payload.location.address) or None,
            latitude=payload.location.latitude,
            longitude=payload.location.longitude,
        )

        position_hint = normalize_whitespace(payload.position_hint) or extract_spatial_hint(
            payload.caption,
            payload.scene_summary,
            payload.note,
        )

        return MemoryDocument(
            memory_id=memory_id,
            user_id=user_id,
            image_key=normalize_whitespace(payload.image_key) or None,
            image_url=normalize_whitespace(payload.image_url) or None,
            captured_at=normalize_whitespace(payload.captured_at) or None,
            caption=normalize_whitespace(payload.caption) or None,
            scene_summary=normalize_whitespace(payload.scene_summary) or None,
            detected_objects=dedupe_strings(payload.detected_objects),
            tags=dedupe_strings(payload.tags),
            ocr_text=normalize_whitespace(payload.ocr_text) or None,
            note=normalize_whitespace(payload.note) or None,
            position_hint=position_hint,
            location=location,
        )

    @staticmethod
    def _require_identifier(value: str, *, field_name: str) -> str:
        normalized = normalize_whitespace(value)
        if not normalized:
            raise ValueError(f"{field_name} must not be blank")
        return normalized
