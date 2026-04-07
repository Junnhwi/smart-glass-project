from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any, Protocol, runtime_checkable

from src.ingestion.models import MemoryDocument

try:  # pragma: no cover - optional runtime dependency
    import psycopg
except ImportError:  # pragma: no cover - handled at runtime
    psycopg = None


@runtime_checkable
class MemoryStore(Protocol):
    def upsert_many(self, documents: list[MemoryDocument]) -> int: ...

    def list_by_user(self, user_id: str) -> list[MemoryDocument]: ...

    def count(self, user_id: str | None = None) -> int: ...

    def readiness_detail(self) -> dict[str, Any]: ...


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
            "backend": "file",
            "path": str(self.storage_path),
            "indexed_documents": self.count(),
        }


class PostgresMemoryStore:
    table_name = "rag_memory_records"

    def __init__(self, database_url: str):
        self.database_url = database_url.strip()
        if not self.database_url:
            raise ValueError("database_url must not be blank")
        self._lock = Lock()
        self._schema_ready = False

    def _require_driver(self) -> None:
        if psycopg is None:
            raise RuntimeError(
                "psycopg is required for the postgres memory store. "
                "Install apps/rag-service requirements."
            )

    def _connect(self):  # type: ignore[no-untyped-def]
        self._require_driver()
        return psycopg.connect(self.database_url)

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return

        with self._lock:
            if self._schema_ready:
                return

            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        CREATE TABLE IF NOT EXISTS {self.table_name} (
                            memory_id TEXT PRIMARY KEY,
                            user_id TEXT NOT NULL,
                            captured_at TEXT,
                            searchable_text TEXT NOT NULL DEFAULT '',
                            document JSONB NOT NULL,
                            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                    cur.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_user_id
                        ON {self.table_name} (user_id)
                        """
                    )
                    cur.execute(
                        f"""
                        CREATE INDEX IF NOT EXISTS idx_{self.table_name}_user_id_captured_at
                        ON {self.table_name} (user_id, captured_at DESC, memory_id DESC)
                        """
                    )
                conn.commit()

            self._schema_ready = True

    def _serialize_document(self, document: MemoryDocument) -> tuple[str, str, str | None, str]:
        return (
            document.memory_id,
            document.user_id,
            document.captured_at,
            document.searchable_text(),
        )

    def upsert_many(self, documents: list[MemoryDocument]) -> int:
        if not documents:
            return 0

        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                for document in documents:
                    memory_id, user_id, captured_at, searchable_text = self._serialize_document(document)
                    cur.execute(
                        f"""
                        INSERT INTO {self.table_name} (
                            memory_id,
                            user_id,
                            captured_at,
                            searchable_text,
                            document,
                            created_at,
                            updated_at
                        ) VALUES (%s, %s, %s, %s, %s::jsonb, NOW(), NOW())
                        ON CONFLICT (memory_id) DO UPDATE SET
                            user_id = EXCLUDED.user_id,
                            captured_at = EXCLUDED.captured_at,
                            searchable_text = EXCLUDED.searchable_text,
                            document = EXCLUDED.document,
                            updated_at = NOW()
                        """,
                        (
                            memory_id,
                            user_id,
                            captured_at,
                            searchable_text,
                            json.dumps(document.to_dict(), ensure_ascii=False),
                        ),
                    )
            conn.commit()

        return len(documents)

    def list_by_user(self, user_id: str) -> list[MemoryDocument]:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT document::text
                    FROM {self.table_name}
                    WHERE user_id = %s
                    ORDER BY (captured_at IS NULL) ASC, captured_at DESC, memory_id DESC
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()

        documents: list[MemoryDocument] = []
        for (document_json,) in rows:
            documents.append(MemoryDocument.from_dict(json.loads(document_json)))
        return documents

    def count(self, user_id: str | None = None) -> int:
        self._ensure_schema()
        with self._connect() as conn:
            with conn.cursor() as cur:
                if user_id is None:
                    cur.execute(f"SELECT COUNT(*) FROM {self.table_name}")
                else:
                    cur.execute(
                        f"SELECT COUNT(*) FROM {self.table_name} WHERE user_id = %s",
                        (user_id,),
                    )
                row = cur.fetchone()
        return int(row[0] if row else 0)

    def readiness_detail(self) -> dict[str, Any]:
        try:
            self._ensure_schema()
            return {
                "status": "ok",
                "backend": "postgres",
                "indexed_documents": self.count(),
            }
        except Exception as exc:
            return {
                "status": "error",
                "backend": "postgres",
                "error": str(exc),
            }
