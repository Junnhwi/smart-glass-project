from collections import defaultdict

from src.api.schemas import MemoryRecordPayload
from src.embedder.tfidf import TfidfTextEmbedder
from src.ingestion.service import MemoryIngestionService
from src.retriever.answering import GeneratedAnswer, OpenAICompatibleAnswerGenerator
from src.retriever.hybrid import HybridMemoryRetriever, SearchHit
from src.utils.config import Settings
from src.vectorstore.store import FileBackedMemoryStore


class RagQueryService:
    def __init__(
        self,
        store: FileBackedMemoryStore,
        ingestion_service: MemoryIngestionService,
        retriever: HybridMemoryRetriever,
        answer_generator: OpenAICompatibleAnswerGenerator,
    ):
        self.store = store
        self.ingestion_service = ingestion_service
        self.retriever = retriever
        self.answer_generator = answer_generator

    @classmethod
    def from_settings(cls, settings: Settings) -> "RagQueryService":
        store = FileBackedMemoryStore(settings.storage_path)
        ingestion_service = MemoryIngestionService()
        retriever = HybridMemoryRetriever(store=store, embedder=TfidfTextEmbedder())
        answer_generator = OpenAICompatibleAnswerGenerator(settings)
        return cls(
            store=store,
            ingestion_service=ingestion_service,
            retriever=retriever,
            answer_generator=answer_generator,
        )

    def index_memories(self, payloads: list[MemoryRecordPayload]) -> dict[str, object]:
        documents = self.ingestion_service.normalize_many(payloads)
        indexed_count = self.store.upsert_many(documents)

        totals: dict[str, int] = defaultdict(int)
        for document in documents:
            totals[document.user_id] = self.store.count(document.user_id)

        return {
            "indexed_count": indexed_count,
            "total_user_memories": dict(totals),
        }

    def search(self, user_id: str, query: str, top_k: int) -> list[SearchHit]:
        return self.retriever.search(user_id=user_id, query=query, top_k=top_k)

    def chat(self, user_id: str, query: str, top_k: int) -> tuple[GeneratedAnswer, list[SearchHit]]:
        hits = self.search(user_id=user_id, query=query, top_k=top_k)
        answer = self.answer_generator.generate(query=query, hits=hits)
        return answer, hits
