from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol

from src.database.memory_store import MemoryRecord, PostgresMemoryStoreClient
from src.modules.search.text import (
    expand_terms,
    extract_spatial_hint,
    format_timestamp,
    humanize_term,
    search_terms_from_query,
)


MAX_CONTEXT_HITS = 2


@dataclass(frozen=True, slots=True)
class SearchHit:
    memory: MemoryRecord
    score: float
    lexical_score: float
    matched_terms: list[str]


@dataclass(frozen=True, slots=True)
class GeneratedAnswer:
    text: str
    mode: str
    cited_memory_ids: list[str] = field(default_factory=list)
    confidence: float | None = None
    reason: str | None = None


class MemorySearchRepository(Protocol):
    def list_by_user(
        self,
        user_id: str,
        *,
        limit: int | None = None,
    ) -> list[MemoryRecord]: ...

    def check_health(self) -> None: ...


class TemplateAnswerGenerator:
    def _describe_subject(self, hit: SearchHit) -> str:
        candidates = [
            *hit.matched_terms,
            *hit.memory.detected_objects,
            *hit.memory.tags,
        ]
        for candidate in candidates:
            label = humanize_term(candidate)
            if label:
                return label
        return "\uCC3E\uC73C\uC2DC\uB294 \uBB3C\uAC74"

    def _describe_location(self, hit: SearchHit) -> str:
        memory = hit.memory
        place = memory.location.name or memory.location.address
        position_hint = (
            extract_spatial_hint(
                memory.position_hint,
                memory.caption,
                memory.scene_summary,
            )
            or memory.position_hint
        )
        formatted_time = format_timestamp(memory.captured_at)

        if place and position_hint:
            summary = (
                f"{place}\uC5D0\uC11C {position_hint}\uC5D0 "
                "\uC788\uC5C8\uB358 \uAC83\uC73C\uB85C \uBCF4\uC5EC\uC694."
            )
        elif position_hint:
            summary = (
                f"{position_hint}\uC5D0 "
                "\uC788\uC5C8\uB358 \uAC83\uC73C\uB85C \uBCF4\uC5EC\uC694."
            )
        elif place:
            summary = f"{place}\uC5D0\uC11C \uD655\uC778\uB410\uC5B4\uC694."
        elif memory.caption:
            summary = (
                "\uC0AC\uC9C4 \uC124\uBA85\uC73C\uB85C\uB294 "
                f"{memory.caption}\uB85C \uAE30\uB85D\uB418\uC5B4 \uC788\uC5B4\uC694."
            )
        else:
            summary = "\uC704\uCE58 \uB2E8\uC11C\uB97C \uCC3E\uC9C0 \uBABB\uD588\uC5B4\uC694."

        if formatted_time:
            summary += (
                f" \uB9C8\uC9C0\uB9C9 \uD655\uC778 \uC2DC\uAC01\uC740 "
                f"{formatted_time}\uC785\uB2C8\uB2E4."
            )
        return summary

    def generate(self, query: str, hits: list[SearchHit]) -> GeneratedAnswer:
        if not hits:
            return GeneratedAnswer(
                text=(
                    "\uAD00\uB828 \uBA54\uBAA8\uB9AC \uAE30\uB85D\uC744 "
                    "\uCC3E\uC9C0 \uBABB\uD588\uC5B4\uC694. "
                    "\uBB3C\uAC74 \uC774\uB984\uC774\uB098 \uC7A5\uC18C "
                    "\uB2E8\uC11C\uB97C \uC870\uAE08 \uB354 \uAD6C\uCCB4\uC801\uC73C\uB85C "
                    "\uB9D0\uD574 \uC8FC\uC138\uC694."
                ),
                mode="template",
                cited_memory_ids=[],
                confidence=None,
                reason="\uAC80\uC0C9 \uACB0\uACFC\uAC00 \uC5C6\uC5B4\uC11C \uD15C\uD50C\uB9BF \uC751\uB2F5\uC744 \uC0AC\uC6A9\uD588\uC2B5\uB2C8\uB2E4.",
            )

        top_hit = hits[0]
        subject = self._describe_subject(top_hit)
        answer_parts = [
            f"\uCC3E\uC73C\uC2E0 {subject}\uC740",
            self._describe_location(top_hit),
        ]

        if len(hits) > 1:
            answer_parts.append(
                f"\uBE44\uC2B7\uD55C \uD6C4\uBCF4\uB3C4 "
                f"{min(len(hits) - 1, MAX_CONTEXT_HITS - 1)}\uAC1C \uB354 \uCC3E\uC558\uC5B4\uC694."
            )

        return GeneratedAnswer(
            text=" ".join(answer_parts),
            mode="template",
            cited_memory_ids=[hit.memory.memory_id for hit in hits[:MAX_CONTEXT_HITS]],
            confidence=0.5,
            reason="\uAC80\uC0C9 \uACB0\uACFC\uB97C \uAE30\uBC18\uC73C\uB85C \uD15C\uD50C\uB9BF \uC751\uB2F5\uC744 \uC0AC\uC6A9\uD588\uC2B5\uB2C8\uB2E4.",
        )


def _overlap_score(query_terms: set[str], candidate_terms: set[str], weight: float) -> float:
    if not query_terms or not candidate_terms:
        return 0.0
    overlap = query_terms & candidate_terms
    if not overlap:
        return 0.0
    return weight * (len(overlap) / len(query_terms))


def _expand_record_terms(record: MemoryRecord) -> tuple[set[str], set[str], set[str], set[str]]:
    object_terms = set(expand_terms(record.detected_objects))
    tag_terms = set(expand_terms(record.tags))
    location_terms = set(
        expand_terms(
            [
                record.location.name or "",
                record.location.address or "",
            ]
        )
    )
    text_terms = set(
        expand_terms(
            [
                record.caption or "",
                record.scene_summary or "",
                record.position_hint or "",
                record.ocr_text or "",
                record.note or "",
            ]
        )
    )
    return object_terms, tag_terms, location_terms, text_terms


class MemoryQueryService:
    def __init__(
        self,
        repository: MemorySearchRepository,
        *,
        default_top_k: int = 5,
        answer_generator: TemplateAnswerGenerator | None = None,
    ) -> None:
        self.repository = repository
        self.default_top_k = max(1, min(default_top_k, 20))
        self.answer_generator = answer_generator or TemplateAnswerGenerator()

    def _search_hits(self, user_id: str, query: str, top_k: int) -> list[SearchHit]:
        documents = self.repository.list_by_user(user_id, limit=max(top_k * 10, 40))
        if not documents:
            return []

        query_terms = set(search_terms_from_query(query))
        if not query_terms:
            return []

        hits: list[SearchHit] = []
        for record in documents:
            object_terms, tag_terms, location_terms, text_terms = _expand_record_terms(record)
            matched_terms = sorted(
                query_terms & (object_terms | tag_terms | location_terms | text_terms)
            )

            lexical_score = 0.0
            lexical_score += _overlap_score(query_terms, object_terms, 0.45)
            lexical_score += _overlap_score(query_terms, tag_terms, 0.2)
            lexical_score += _overlap_score(query_terms, location_terms, 0.2)
            lexical_score += _overlap_score(query_terms, text_terms, 0.15)
            if lexical_score <= 0:
                continue

            hits.append(
                SearchHit(
                    memory=record,
                    score=round(lexical_score, 6),
                    lexical_score=round(lexical_score, 6),
                    matched_terms=matched_terms,
                )
            )

        hits.sort(
            key=lambda item: (item.score, item.memory.captured_at or "", item.memory.memory_id),
            reverse=True,
        )
        return hits[:top_k]

    def search(self, user_id: str, query: str, top_k: int | None = None) -> list[SearchHit]:
        resolved_top_k = top_k if isinstance(top_k, int) and top_k > 0 else self.default_top_k
        return self._search_hits(user_id, query, min(resolved_top_k, 20))

    def chat(
        self,
        user_id: str,
        query: str,
        top_k: int | None = None,
    ) -> tuple[GeneratedAnswer, list[SearchHit]]:
        hits = self.search(user_id, query, top_k)
        answer = self.answer_generator.generate(query, hits)
        return answer, hits

    def check_health(self) -> None:
        self.repository.check_health()


def build_default_memory_query_service() -> MemoryQueryService:
    database_url = os.getenv("API_CAPTURE_DATABASE_URL", "").strip()
    if not database_url:
        raise ValueError("API_CAPTURE_DATABASE_URL is required for memory queries")
    top_k_raw = os.getenv("API_MEMORY_DEFAULT_TOP_K", "5").strip() or "5"
    return MemoryQueryService(
        PostgresMemoryStoreClient(database_url),
        default_top_k=max(1, min(int(top_k_raw), 20)),
    )
