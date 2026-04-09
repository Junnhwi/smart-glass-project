import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from src.ingestion.models import MemoryDocument, MemoryLocation
from src.retriever.service import RagQueryService
from src.utils.config import Settings
from src.vectorstore import store as store_module
from src.vectorstore.store import PostgresMemoryStore


class _FakeCursor:
    def __init__(self, state: dict[str, object]):
        self._state = state
        self._results: list[tuple[object, ...]] = []

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> None:
        normalized = " ".join(query.split()).lower()
        rows = self._state.setdefault("rows", {})  # type: ignore[assignment]

        if normalized.startswith("create extension if not exists vector"):
            return
        if normalized.startswith("create table if not exists"):
            return
        if normalized.startswith("alter table rag_memory_records add column if not exists embedding vector"):
            return
        if normalized.startswith("create index if not exists"):
            return

        if normalized.startswith("insert into rag_memory_records"):
            assert params is not None
            if len(params) == 5:
                memory_id, user_id, captured_at, searchable_text, document_json = params
                embedding = None
            else:
                memory_id, user_id, captured_at, searchable_text, embedding, document_json = params
            rows[memory_id] = {
                "memory_id": memory_id,
                "user_id": user_id,
                "captured_at": captured_at,
                "searchable_text": searchable_text,
                "embedding": embedding,
                "document": json.loads(document_json),
            }
            return

        if normalized.startswith(
            "select document::text from rag_memory_records where user_id = %s"
        ):
            assert params is not None
            user_id = params[0]
            matched_rows = [
                row for row in rows.values() if row["user_id"] == user_id
            ]
            matched_rows.sort(key=lambda row: row["memory_id"], reverse=True)
            matched_rows.sort(key=lambda row: row["captured_at"] or "", reverse=True)
            matched_rows.sort(key=lambda row: row["captured_at"] is None)
            self._results = [
                (json.dumps(row["document"], ensure_ascii=False),)
                for row in matched_rows
            ]
            return

        if normalized.startswith("select count(*) from rag_memory_records where user_id = %s"):
            assert params is not None
            user_id = params[0]
            count = sum(1 for row in rows.values() if row["user_id"] == user_id)
            self._results = [(count,)]
            return

        if normalized.startswith("select count(*) from rag_memory_records"):
            self._results = [(len(rows),)]
            return

        raise AssertionError(f"Unexpected SQL: {query}")

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._results

    def fetchone(self) -> tuple[object, ...] | None:
        return self._results[0] if self._results else None

    def __enter__(self) -> "_FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeConnection:
    def __init__(self, state: dict[str, object]):
        self._state = state

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self._state)

    def commit(self) -> None:
        return None

    def __enter__(self) -> "_FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class PostgresMemoryStoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.state: dict[str, object] = {"rows": {}}
        self.psycopg_patch = patch.object(
            store_module,
            "psycopg",
            types.SimpleNamespace(connect=self._connect),
        )
        self.psycopg_patch.start()

    def tearDown(self) -> None:
        self.psycopg_patch.stop()

    def _connect(self, database_url: str) -> _FakeConnection:
        self.state["database_url"] = database_url
        return _FakeConnection(self.state)

    def _build_document(self, memory_id: str, captured_at: str) -> MemoryDocument:
        return MemoryDocument(
            memory_id=memory_id,
            user_id="user-1",
            image_key=f"captures/{memory_id}.jpg",
            image_url=None,
            captured_at=captured_at,
            caption="an umbrella is leaning against the sofa",
            scene_summary="living room scene",
            detected_objects=["umbrella", "sofa"],
            tags=["umbrella"],
            ocr_text=None,
            note=None,
            position_hint="sofa beside",
            location=MemoryLocation(name="living room"),
        )

    def test_round_trip_and_count(self) -> None:
        store = PostgresMemoryStore("postgresql://example")

        written = store.upsert_many(
            [
                self._build_document("mem-umbrella-01", "2026-04-06T12:00:00Z"),
                self._build_document("mem-umbrella-02", "2026-04-06T13:00:00Z"),
            ]
        )

        self.assertEqual(written, 2)
        self.assertEqual(store.count(), 2)
        self.assertEqual(store.count("user-1"), 2)

        documents = store.list_by_user("user-1")
        self.assertEqual(
            [document.memory_id for document in documents],
            ["mem-umbrella-02", "mem-umbrella-01"],
        )
        self.assertEqual(documents[0].location.name, "living room")
        self.assertEqual(documents[0].tags, ["umbrella"])

        readiness = store.readiness_detail()
        self.assertEqual(readiness["status"], "ok")
        self.assertEqual(readiness["backend"], "postgres")
        self.assertEqual(readiness["indexed_documents"], 2)
        self.assertEqual(self.state["database_url"], "postgresql://example")


class RagQueryServiceStorageSelectionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings_kwargs = dict(
            service_name="rag-service",
            storage_path=Path(self.temp_dir.name) / "memory_store.json",
            default_top_k=5,
            llm_api_key="",
            llm_base_url=None,
            llm_model="",
            llm_timeout_sec=20.0,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_from_settings_uses_postgres_store_when_configured(self) -> None:
        with (
            patch("src.retriever.service.PostgresMemoryStore") as postgres_store,
            patch("src.retriever.service.FileBackedMemoryStore") as file_store,
        ):
            postgres_store.return_value = object()
            file_store.return_value = object()

            settings = Settings(
                **self.settings_kwargs,
                storage_backend="postgres",
                database_url="postgresql://example",
            )
            RagQueryService.from_settings(settings)

        postgres_store.assert_called_once_with("postgresql://example")
        file_store.assert_not_called()

    def test_from_settings_defaults_to_file_store(self) -> None:
        with (
            patch("src.retriever.service.PostgresMemoryStore") as postgres_store,
            patch("src.retriever.service.FileBackedMemoryStore") as file_store,
        ):
            postgres_store.return_value = object()
            file_store.return_value = object()

            settings = Settings(**self.settings_kwargs)
            RagQueryService.from_settings(settings)

        file_store.assert_called_once()
        postgres_store.assert_not_called()


if __name__ == "__main__":
    unittest.main()
