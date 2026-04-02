import json
from pathlib import Path
from threading import Lock
from typing import Any

from src.ingestion.models import MemoryDocument


class FileBackedMemoryStore:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self._lock = Lock()
        self._documents: dict[str, dict[str, MemoryDocument]] = {}
        self._load()

    def _load(self) -> None:
        if not self.storage_path.exists():
            return

        raw = self.storage_path.read_text(encoding="utf-8").strip()
        if not raw:
            return

        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValueError("Stored memory data must be a JSON array")

        for item in payload:
            document = MemoryDocument.from_dict(item)
            self._documents.setdefault(document.user_id, {})[document.memory_id] = document

    def _save(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            document.to_dict()
            for user_documents in self._documents.values()
            for document in user_documents.values()
        ]
        payload.sort(key=lambda item: (item["user_id"], item["memory_id"]))

        temp_path = self.storage_path.with_suffix(f"{self.storage_path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.storage_path)

    def upsert_many(self, documents: list[MemoryDocument]) -> int:
        with self._lock:
            for document in documents:
                user_documents = self._documents.setdefault(document.user_id, {})
                user_documents[document.memory_id] = document
            self._save()
        return len(documents)

    def list_by_user(self, user_id: str) -> list[MemoryDocument]:
        documents = list(self._documents.get(user_id, {}).values())
        return sorted(
            documents,
            key=lambda item: item.captured_at or "",
            reverse=True,
        )

    def count(self, user_id: str | None = None) -> int:
        if user_id is not None:
            return len(self._documents.get(user_id, {}))
        return sum(len(user_documents) for user_documents in self._documents.values())

    def readiness_detail(self) -> dict[str, Any]:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        return {
            "status": "ok",
            "path": str(self.storage_path),
            "indexed_documents": self.count(),
        }
