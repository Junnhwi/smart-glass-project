from dataclasses import dataclass
from typing import Any

from src.utils.text import dedupe_strings, expand_terms, normalize_whitespace


@dataclass(slots=True)
class MemoryLocation:
    name: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    def as_text(self) -> str:
        return " ".join(
            dedupe_strings(
                [
                    self.name,
                    self.address,
                ]
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "address": self.address,
            "latitude": self.latitude,
            "longitude": self.longitude,
        }


@dataclass(slots=True)
class MemoryDocument:
    memory_id: str
    user_id: str
    image_key: str | None
    image_url: str | None
    captured_at: str | None
    caption: str | None
    scene_summary: str | None
    detected_objects: list[str]
    tags: list[str]
    ocr_text: str | None
    note: str | None
    position_hint: str | None
    location: MemoryLocation

    def searchable_text(self) -> str:
        raw_fields = [
            self.caption or "",
            self.scene_summary or "",
            self.ocr_text or "",
            self.note or "",
            self.position_hint or "",
            self.location.as_text(),
            " ".join(self.detected_objects),
            " ".join(self.tags),
        ]
        expanded_terms = expand_terms(raw_fields)
        return " ".join(dedupe_strings([*raw_fields, " ".join(expanded_terms)]))

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "user_id": self.user_id,
            "image_key": self.image_key,
            "image_url": self.image_url,
            "captured_at": self.captured_at,
            "caption": self.caption,
            "scene_summary": self.scene_summary,
            "detected_objects": self.detected_objects,
            "tags": self.tags,
            "ocr_text": self.ocr_text,
            "note": self.note,
            "position_hint": self.position_hint,
            "location": self.location.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MemoryDocument":
        location_payload = payload.get("location") or {}
        location = MemoryLocation(
            name=normalize_whitespace(location_payload.get("name")) or None,
            address=normalize_whitespace(location_payload.get("address")) or None,
            latitude=location_payload.get("latitude"),
            longitude=location_payload.get("longitude"),
        )
        return cls(
            memory_id=normalize_whitespace(payload.get("memory_id")),
            user_id=normalize_whitespace(payload.get("user_id")),
            image_key=normalize_whitespace(payload.get("image_key")) or None,
            image_url=normalize_whitespace(payload.get("image_url")) or None,
            captured_at=normalize_whitespace(payload.get("captured_at")) or None,
            caption=normalize_whitespace(payload.get("caption")) or None,
            scene_summary=normalize_whitespace(payload.get("scene_summary")) or None,
            detected_objects=dedupe_strings(payload.get("detected_objects", [])),
            tags=dedupe_strings(payload.get("tags", [])),
            ocr_text=normalize_whitespace(payload.get("ocr_text")) or None,
            note=normalize_whitespace(payload.get("note")) or None,
            position_hint=normalize_whitespace(payload.get("position_hint")) or None,
            location=location,
        )
