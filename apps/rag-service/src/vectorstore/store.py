from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Protocol, runtime_checkable

import numpy as np

from src.embedder.hashing import HashingTextEmbedder
from src.ingestion.models import MemoryDocument
from src.utils.text import build_search_query_text

try:  # pragma: no cover - optional runtime dependency
    import psycopg
except ImportError:  # pragma: no cover - handled at runtime
    psycopg = None

try:  # pragma: no cover - optional runtime dependency
    from pgvector.psycopg import register_vector
except ImportError:  # pragma: no cover - handled at runtime
    register_vector = None


@dataclass(slots=True)
class VectorSearchResult:
    memory: MemoryDocument
    similarity: float


MIN_VECTOR_SIMILARITY = 0.15


@runtime_checkable
class MemoryStore(Protocol):
    def upsert_many(self, documents: list[MemoryDocument]) -> int: ...

    def list_by_user(self, user_id: str) -> list[MemoryDocument]: ...

    def count(self, user_id: str | None = None) -> int: ...

    def readiness_detail(self) -> dict[str, Any]: ...

    def search_similar(
        self,
        user_id: str,
        query: str,
        top_k: int,
    ) -> list[VectorSearchResult]: ...


class FileBackedMemoryStore:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self._lock = Lock()
        self._documents: dict[str, dict[str, MemoryDocument]] = {}
        self._embedder = HashingTextEmbedder()
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

    def search_similar(
        self,
        user_id: str,
        query: str,
        top_k: int,
    ) -> list[VectorSearchResult]:
        documents = self.list_by_user(user_id)
        if not documents:
            return []

        search_query = build_search_query_text(query)
        query_embedding = self._embedder.embed(search_query)
        if query_embedding is None:
            return []

        hits: list[VectorSearchResult] = []
        for document in documents:
            document_embedding = self._embedder.embed(document.searchable_text())
            if document_embedding is None:
                continue

            similarity = float(np.dot(query_embedding.values, document_embedding.values))
            if similarity < MIN_VECTOR_SIMILARITY:
                continue

            hits.append(
                VectorSearchResult(
                    memory=document,
                    similarity=round(similarity, 6),
                )
            )

        hits.sort(
            key=lambda item: (
                item.similarity,
                item.memory.captured_at or "",
                item.memory.memory_id,
            ),
            reverse=True,
        )
        return hits[:top_k]

    def readiness_detail(self) -> dict[str, Any]:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        return {
            "status": "ok",
            "backend": "file",
            "path": str(self.storage_path),
            "indexed_documents": self.count(),
            "vector_dimension": self._embedder.dimension,
        }


class PostgresMemoryStore:
    table_name = "rag_memory_records"
    embedding_dimension = 384

    def __init__(self, database_url: str):
        self.database_url = database_url.strip()
        if not self.database_url:
            raise ValueError("database_url must not be blank")
        self._lock = Lock()
        self._schema_ready = False
        self._embedder = HashingTextEmbedder(self.embedding_dimension)

    def _require_driver(self) -> None:
        if psycopg is None:
            raise RuntimeError(
                "psycopg is required for the postgres memory store. "
                "Install apps/rag-service requirements."
            )

    def _connect(self, register_vector_type: bool = False):  # type: ignore[no-untyped-def]
        self._require_driver()
        conn = psycopg.connect(self.database_url)
        if (
            register_vector_type
            and register_vector is not None
            and hasattr(psycopg, "Connection")
            and isinstance(conn, psycopg.Connection)
        ):
            register_vector(conn)
        return conn

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return

        with self._lock:
            if self._schema_ready:
                return

            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public'
                          AND table_name = %s
                        LIMIT 1
                        """,
                        (self.table_name,),
                    )
                    table_row = cur.fetchone()
                    if table_row is None:
                        raise RuntimeError(
                            f"Schema table {self.table_name} is missing. "
                            "Run Alembic migrations before using the postgres memory store."
                        )

                    cur.execute(
                        """
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = %s
                          AND column_name = %s
                        LIMIT 1
                        """,
                        (self.table_name, "embedding"),
                    )
                    embedding_row = cur.fetchone()
                    if embedding_row is None:
                        raise RuntimeError(
                            f"Schema column embedding is missing from {self.table_name}. "
                            "Run Alembic migrations before using the postgres memory store."
                        )

                    cur.execute(
                        """
                        SELECT kcu.column_name
                        FROM information_schema.table_constraints AS tc
                        JOIN information_schema.key_column_usage AS kcu
                          ON tc.constraint_name = kcu.constraint_name
                         AND tc.table_schema = kcu.table_schema
                        WHERE tc.table_schema = 'public'
                          AND tc.table_name = %s
                          AND tc.constraint_type = 'PRIMARY KEY'
                        ORDER BY kcu.ordinal_position
                        """,
                        (self.table_name,),
                    )
                    primary_key_columns = [row[0] for row in cur.fetchall()]
                    if primary_key_columns != ["user_id", "memory_id"]:
                        raise RuntimeError(
                            f"Schema primary key for {self.table_name} must be "
                            "(user_id, memory_id). Run Alembic migrations before "
                            "using the postgres memory store."
                        )

            self._schema_ready = True

    def _serialize_document(
        self,
        document: MemoryDocument,
    ) -> tuple[str, str, str | None, str, np.ndarray | None]:
        searchable_text = document.searchable_text()
        embedding = self._embedder.embed(searchable_text)
        return (
            document.memory_id,
            document.user_id,
            document.captured_at,
            searchable_text,
            embedding.values if embedding is not None else None,
        )

    def upsert_many(self, documents: list[MemoryDocument]) -> int:
        if not documents:
            return 0

        self._ensure_schema()
        with self._connect(register_vector_type=True) as conn:
            with conn.cursor() as cur:
                for document in documents:
                    (
                        memory_id,
                        user_id,
                        captured_at,
                        searchable_text,
                        embedding,
                    ) = self._serialize_document(document)
                    cur.execute(
                        f"""
                        INSERT INTO {self.table_name} (
                            memory_id,
                            user_id,
                            captured_at,
                            searchable_text,
                            embedding,
                            document,
                            created_at,
                            updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW(), NOW())
                        ON CONFLICT (user_id, memory_id) DO UPDATE SET
                            captured_at = EXCLUDED.captured_at,
                            searchable_text = EXCLUDED.searchable_text,
                            embedding = EXCLUDED.embedding,
                            document = EXCLUDED.document,
                            updated_at = NOW()
                        """,
                        (
                            memory_id,
                            user_id,
                            captured_at,
                            searchable_text,
                            embedding,
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

    def search_similar(
        self,
        user_id: str,
        query: str,
        top_k: int,
    ) -> list[VectorSearchResult]:
        self._ensure_schema()
        search_query = build_search_query_text(query)
        query_embedding = self._embedder.embed(search_query)
        if query_embedding is None:
            return []

        with self._connect(register_vector_type=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT document::text, 1 - (embedding <=> %s) AS similarity
                    FROM {self.table_name}
                    WHERE user_id = %s
                      AND embedding IS NOT NULL
                    ORDER BY embedding <=> %s, captured_at DESC, memory_id DESC
                    LIMIT %s
                    """,
                    (
                        query_embedding.values,
                        user_id,
                        query_embedding.values,
                        top_k,
                    ),
                )
                rows = cur.fetchall()

        hits: list[VectorSearchResult] = []
        for document_json, similarity in rows:
            score = round(float(similarity or 0.0), 6)
            if score < MIN_VECTOR_SIMILARITY:
                continue
            hits.append(
                VectorSearchResult(
                    memory=MemoryDocument.from_dict(json.loads(document_json)),
                    similarity=score,
                )
            )
        return hits

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
                "vector_dimension": self.embedding_dimension,
            }
        except Exception as exc:
            return {
                "status": "error",
                "backend": "postgres",
                "error": str(exc),
            }
