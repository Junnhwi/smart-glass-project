import unittest

from src.embedder.tfidf import TfidfTextEmbedder
from src.ingestion.models import MemoryDocument, MemoryLocation
from src.retriever.hybrid import HybridMemoryRetriever, SearchHit
from src.vectorstore.store import VectorSearchResult


class _FakeStore:
    def __init__(
        self,
        documents: list[MemoryDocument],
        vector_hits: list[VectorSearchResult],
    ) -> None:
        self._documents = documents
        self._vector_hits = vector_hits

    def list_by_user(self, user_id: str) -> list[MemoryDocument]:
        return [document for document in self._documents if document.user_id == user_id]

    def search_similar(self, user_id: str, query: str, top_k: int) -> list[VectorSearchResult]:
        return self._vector_hits[:top_k]


class HybridMemoryRetrieverTestCase(unittest.TestCase):
    def _build_document(
        self,
        *,
        memory_id: str,
        caption: str,
        objects: list[str],
    ) -> MemoryDocument:
        return MemoryDocument(
            memory_id=memory_id,
            user_id="user-1",
            image_key=f"captures/{memory_id}.jpg",
            image_url=None,
            captured_at="2026-04-06T12:00:00Z",
            caption=caption,
            scene_summary="desk scene",
            detected_objects=objects,
            tags=objects,
            ocr_text=None,
            note=None,
            position_hint=None,
            location=MemoryLocation(name="office"),
        )

    def test_search_keeps_relevant_document_even_when_vector_hits_are_sparse(self) -> None:
        relevant = self._build_document(
            memory_id="mem-umbrella",
            caption="an umbrella is leaning against the sofa",
            objects=["umbrella", "sofa"],
        )
        decoy = self._build_document(
            memory_id="mem-apple",
            caption="an apple is on the table",
            objects=["apple", "table"],
        )
        store = _FakeStore(
            documents=[relevant, decoy],
            vector_hits=[VectorSearchResult(memory=decoy, similarity=0.98)],
        )
        retriever = HybridMemoryRetriever(store=store, embedder=TfidfTextEmbedder())

        hits = retriever.search("user-1", "where is the umbrella", top_k=1)

        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0].memory.memory_id, "mem-umbrella")
        self.assertIsInstance(hits[0], SearchHit)


if __name__ == "__main__":
    unittest.main()
