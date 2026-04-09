from dataclasses import dataclass

from src.embedder.tfidf import TfidfTextEmbedder
from src.ingestion.models import MemoryDocument
from src.utils.text import expand_terms, normalize_search_query, tokenize_text
from src.vectorstore.store import MemoryStore


def _overlap_score(query_terms: set[str], candidate_terms: set[str], weight: float) -> float:
    if not query_terms or not candidate_terms:
        return 0.0
    overlap = query_terms & candidate_terms
    if not overlap:
        return 0.0
    return weight * (len(overlap) / len(query_terms))


@dataclass(slots=True)
class SearchHit:
    memory: MemoryDocument
    score: float
    lexical_score: float
    matched_terms: list[str]
    vector_score: float = 0.0


class HybridMemoryRetriever:
    def __init__(self, store: MemoryStore, embedder: TfidfTextEmbedder):
        self.store = store
        self.embedder = embedder

    def search(self, user_id: str, query: str, top_k: int) -> list[SearchHit]:
        candidate_limit = max(top_k * 5, 20)
        vector_hits = self.store.search_similar(user_id=user_id, query=query, top_k=candidate_limit)
        documents = [hit.memory for hit in vector_hits] if vector_hits else self.store.list_by_user(user_id)
        if not documents:
            return []

        normalized_query = normalize_search_query(query)
        query_terms = set(expand_terms(tokenize_text(normalized_query)))
        query_text = " ".join([normalized_query, *sorted(query_terms)])
        search_texts = [document.searchable_text() for document in documents]
        vector_scores = {hit.memory.memory_id: hit.similarity for hit in vector_hits}

        index = self.embedder.build_index(search_texts)
        lexical_scores = self.embedder.score_query(index, query_text)
        if not lexical_scores:
            lexical_scores = [0.0] * len(documents)

        hits: list[SearchHit] = []
        for document, lexical_score in zip(documents, lexical_scores, strict=True):
            vector_score = vector_scores.get(document.memory_id, 0.0)
            object_terms = set(expand_terms(document.detected_objects))
            tag_terms = set(expand_terms(document.tags))
            location_terms = set(expand_terms([document.location.as_text()]))
            caption_terms = set(
                expand_terms(
                    [
                        document.caption or "",
                        document.scene_summary or "",
                        document.position_hint or "",
                    ]
                )
            )
            matched_terms = sorted(
                query_terms & (object_terms | tag_terms | location_terms | caption_terms)
            )

            score = lexical_score
            score += vector_score * 0.2
            score += _overlap_score(query_terms, object_terms, 0.45)
            score += _overlap_score(query_terms, tag_terms, 0.2)
            score += _overlap_score(query_terms, location_terms, 0.2)
            score += _overlap_score(query_terms, caption_terms, 0.15)

            if score <= 0:
                continue

            hits.append(
                SearchHit(
                    memory=document,
                    score=round(score, 6),
                    lexical_score=round(float(lexical_score), 6),
                    matched_terms=matched_terms,
                    vector_score=round(float(vector_score), 6),
                )
            )

        hits.sort(key=lambda item: (item.score, item.memory.captured_at or ""), reverse=True)
        return hits[:top_k]
