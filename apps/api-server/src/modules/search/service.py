from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

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


class ChatHttpClient(Protocol):
    def post(self, url: str, *args: Any, **kwargs: Any): ...


class AnswerGenerator(Protocol):
    def generate(self, query: str, hits: list[SearchHit]) -> GeneratedAnswer: ...


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


class OllamaChatClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_sec: float = 20.0,
        http_client: ChatHttpClient | None = None,
    ) -> None:
        self.base_url = self._normalize_text(base_url)
        self.model = self._normalize_text(model)
        self.api_key = self._normalize_text(api_key) or None
        self.timeout_sec = max(5.0, float(timeout_sec))
        self.http_client = http_client or httpx

        if not self.base_url:
            raise ValueError("API_LLM_OLLAMA_BASE_URL is required")
        if not self.model:
            raise ValueError("API_LLM_OLLAMA_MODEL is required")
        if self.base_url.startswith("https://ollama.com") and not self.api_key:
            raise ValueError("API_LLM_OLLAMA_API_KEY is required for Ollama cloud")

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None:
            return ""
        return " ".join(str(value).strip().split())

    def chat(self, *, messages: list[dict[str, str]]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = self.http_client.post(
            f"{self.base_url.rstrip('/')}/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
            },
            headers=headers,
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Ollama chat response is invalid")

        message = payload.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("Ollama chat response is missing message")

        content = self._normalize_text(message.get("content"))
        if not content:
            raise RuntimeError("Ollama chat response is missing content")
        return content


# ---------------------------------------------------------------------------
# Gemma3 LLM Client (Gemma3-optimised parameters)
# ---------------------------------------------------------------------------

class GemmaLLMClient:
    """
    Gemma3-optimised Ollama chat client.
    - temperature=0.3 (grounded RAG)
    - repeat_penalty=1.0 (Gemma3 does not need aggressive penalty)
    - num_ctx=4096 (accommodates rich VLM context)
    - Provides a single-turn call(system, user) helper.
    - Strips LLM-style markdown artefacts from final output.
    """

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_sec: float = 60.0,
        http_client: ChatHttpClient | None = None,
    ) -> None:
        self.base_url = " ".join((base_url or "").strip().split())
        self.model = " ".join((model or "").strip().split())
        self.api_key = " ".join((api_key or "").strip().split()) or None
        self.timeout_sec = max(5.0, float(timeout_sec))
        self.http_client = http_client or httpx

        if not self.base_url:
            raise ValueError("API_LLM_OLLAMA_BASE_URL is required")
        if not self.model:
            raise ValueError("API_LLM_OLLAMA_MODEL is required")

    def call(self, *, system: str, user: str) -> str:
        """Single-turn structured call with Gemma3 options."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": 0.3,
                "repeat_penalty": 1.0,
                "num_ctx": 4096,
            },
        }
        try:
            resp = self.http_client.post(
                f"{self.base_url.rstrip('/')}/chat",
                json=body,
                headers=headers,
                timeout=self.timeout_sec,
            )
            resp.raise_for_status()
        except Exception as exc:
            raise RuntimeError(f"Gemma LLM call failed: {exc}") from exc

        payload = resp.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Gemma LLM response is invalid")
        content: str = (
            (payload.get("message") or {}).get("content") or ""
        ).strip()
        return content

    @staticmethod
    def clean_output(text: str) -> str:
        """Remove markdown artefacts so answers read naturally."""
        import re
        text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"^[\-\*•]\s+", "", text, flags=re.MULTILINE)
        text = re.sub(r"\(?image_key\s*:\s*\S+\)?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()


# ---------------------------------------------------------------------------
# Stage 1 – Intent Analysis
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class _IntentResult:
    target_object: str
    intent_summary: str


_INTENT_SYSTEM = """\
[역할]
당신은 스마트 글라스 기억 보조 시스템의 의도 분석 모듈입니다.
사용자 발화에서 찾고 있는 핵심 사물(명사)을 추출하는 것이 유일한 임무입니다.

[출력 규칙]
- 반드시 아래 형식의 JSON 하나만 출력하세요. 설명이나 마크다운은 절대 포함하지 마세요.
- {"target_object": "<한국어 명사>", "intent_summary": "<한 문장 한국어 요약>"}
- target_object: 브랜드명은 그대로 유지하세요 (예: 에어팟, 애플워치, 갤럭시버즈).
- intent_summary: 사용자가 무엇을 원하는지 한 문장으로 설명하세요.
"""

_INTENT_USER_TMPL = """\
[사용자 발화]
"{query}"
"""


def _run_intent_analysis(client: GemmaLLMClient, query: str) -> _IntentResult:
    import json as _json
    import re as _re

    try:
        raw = client.call(system=_INTENT_SYSTEM, user=_INTENT_USER_TMPL.format(query=query))
        match = _re.search(r"\{.*\}", raw, _re.DOTALL)
        if match:
            parsed = _json.loads(match.group(0))
            return _IntentResult(
                target_object=(parsed.get("target_object") or query).strip(),
                intent_summary=(parsed.get("intent_summary") or "").strip(),
            )
    except Exception:
        pass
    return _IntentResult(target_object=query.strip(), intent_summary="")


# ---------------------------------------------------------------------------
# Stage 2 – Query Expansion (VLM-context-aware)
# ---------------------------------------------------------------------------

_EXPANSION_SYSTEM = """\
[역할]
당신은 한국어 사물 검색 시스템의 쿼리 확장 모듈입니다.

[지침]
- 사용자가 찾는 사물명과 VLM(시각 AI)이 실제로 촬영된 장면에서 교배한 모든 정보를 참고하여
  검색에 활용할 수 있는 유사어·브랜드명·상위어·하위어 목록을 생성하세요.
- 반드시 아래 형식의 JSON 하나만 출력하세요. JSON 외 텍스트는 절대 포함하지 마세요.
- {"expanded_terms": ["term1", "term2", ...]}
- VLM이 감지한 사물 중 찾는 사물과 의미적으로 관련 있는 항목도 포함하세요.
- 실제 현장에 있는 사물명은 원문 그대로 포함하세요.
- 최대 14개 이내로 작성하세요.
"""

_EXPANSION_USER_TMPL = """\
[검색 대상 사물]
{target_object}

[VLM이 기억 기록에서 실제 감지한 사물 목록]
{vlm_objects}

[VLM 장면 태그]
{vlm_tags}

[VLM 장면 설명 (caption)]
{vlm_caption}

[VLM 장면 요약]
{vlm_summary}

[VLM 전체 위치 힌트]
{vlm_position}

[VLM 촬영 장소]
{vlm_location}
"""


def _collect_vlm_expansion_context(records: list[MemoryRecord]) -> dict[str, str]:
    all_objects: list[str] = []
    all_tags: list[str] = []
    captions: list[str] = []
    summaries: list[str] = []
    positions: list[str] = []
    locations: list[str] = []

    for rec in records:
        all_objects.extend(rec.detected_objects)
        all_tags.extend(rec.tags)
        if rec.caption:
            captions.append(rec.caption)
        if rec.scene_summary:
            summaries.append(rec.scene_summary)
        if rec.position_hint:
            positions.append(rec.position_hint)
        loc = rec.location
        if loc.name:
            locations.append(loc.name)
        elif loc.address:
            locations.append(loc.address)
        # pipeline_output 내 개별 사물명도 수집
        po = rec.pipeline_output
        if isinstance(po, dict):
            for obj in po.get("objects", []):
                name = obj.get("name", "")
                if name:
                    all_objects.append(name)

    def _dedup(lst: list[str]) -> str:
        return ", ".join(dict.fromkeys(x for x in lst if x)) or "(없음)"

    return {
        "vlm_objects": _dedup(all_objects),
        "vlm_tags": _dedup(all_tags),
        "vlm_caption": _dedup(captions),
        "vlm_summary": _dedup(summaries),
        "vlm_position": _dedup(positions),
        "vlm_location": _dedup(locations),
    }


def _run_query_expansion(
    client: GemmaLLMClient,
    target_object: str,
    records: list[MemoryRecord],
) -> list[str]:
    import json as _json
    import re as _re

    ctx = _collect_vlm_expansion_context(records)
    try:
        raw = client.call(
            system=_EXPANSION_SYSTEM,
            user=_EXPANSION_USER_TMPL.format(target_object=target_object, **ctx),
        )
        match = _re.search(r"\{.*\}", raw, _re.DOTALL)
        if match:
            parsed = _json.loads(match.group(0))
            terms = parsed.get("expanded_terms", [])
            if isinstance(terms, list):
                return [str(t).strip() for t in terms if str(t).strip()]
    except Exception:
        pass
    return [target_object]


# ---------------------------------------------------------------------------
# Stage 3 – Answer Generation (Gemma3-optimised)
# ---------------------------------------------------------------------------

_ANSWER_SYSTEM = """\
[역할]
당신은 스마트 글라스 착용자의 일상 기억을 도와주는 친근하고 자연스러운 한국어 AI 도우미 Memobot입니다.

[지침]
1. 반드시 자연스러운 구어체 한국어(~요/~어요 체)로만 답변하세요.
2. 마크다운(**굵게**, ## 제목, - 목록 등)을 절대 사용하지 마세요.
3. image_key, memory_id, score 같은 기술적인 필드명은 언급하지 마세요.
4. 기록에 없는 정보는 절대 추측하거나 지어내지 마세요.
5. 가장 최근 기록의 위치 정보(위치 힌트, 주변 사물, 장면 요약)를 활용해 구체적으로 안내하세요.
6. 답변은 2~3문장 이내로 간결하게 작성하세요.
"""

_ANSWER_USER_TMPL = """\
[사용자 질문]
{query}

[검색된 기억 기록 (최신순)]
{context}

위 기록만을 근거로 사용자의 질문에 자연스럽게 답변하세요.
기록에 찾는 사물이 없으면 "기록을 찾지 못했다"고 솔직하게 말하고 다른 이름으로 다시 물어보라고 안내하세요.
"""


def _format_hit_context_gemma(index: int, hit: SearchHit) -> str:
    """MemoryRecord의 모든 VLM 필드를 Gemma3 답변 컨텍스트로 포맷."""
    memory = hit.memory
    captured_str = format_timestamp(memory.captured_at) or memory.captured_at or "알 수 없음"
    scene = memory.scene_summary or memory.caption or "알 수 없음"
    position = memory.position_hint or "알 수 없음"
    objects_str = ", ".join(memory.detected_objects[:10]) if memory.detected_objects else "없음"

    loc = memory.location
    location_str = loc.name or loc.address or "정보 없음"
    ocr_str = memory.ocr_text or ""
    note_str = memory.note or ""

    # pipeline_output 내 개별 사물별 상세 위치 정보 포맷팅
    pipeline_detail = ""
    po = memory.pipeline_output
    if isinstance(po, dict):
        obj_lines = []
        for obj in po.get("objects", []):
            name = obj.get("name", "")
            pos = obj.get("position", {})
            hint = pos.get("hint", "") or pos.get("positionHint") or pos.get("position_hint") or ""
            surface = pos.get("surface") or ""
            nearby = ", ".join(obj.get("nearby_objects") or obj.get("nearby") or [])
            if name:
                detail = f"  · {name}"
                if hint:
                    detail += f" — {hint}"
                if surface:
                    detail += f" ({surface})"
                if nearby:
                    detail += f", 주변: {nearby}"
                obj_lines.append(detail)
        if obj_lines:
            pipeline_detail = "\n- 사물별 상세 위치:\n" + "\n".join(obj_lines)

    lines = [
        f"[기록 {index}]",
        f"- 촬영 시각: {captured_str}",
        f"- 촬영 장소: {location_str}",
        f"- 장면 요약: {scene}",
        f"- 전체 위치 힌트: {position}",
        f"- 감지된 사물 목록: {objects_str}",
    ]
    if pipeline_detail:
        lines.append(pipeline_detail)
    if ocr_str:
        lines.append(f"- 이미지 내 텍스트(OCR): {ocr_str}")
    if note_str:
        lines.append(f"- 사용자 메모: {note_str}")
    return "\n".join(lines) + "\n"


def _run_answer_generation(
    client: GemmaLLMClient,
    query: str,
    hits: list[SearchHit],
    max_hits: int = 3,
) -> str:
    if not hits:
        return "해당 물건에 대한 최근 기록을 찾지 못했어요. 다른 이름이나 설명으로 다시 물어봐 주시겠어요?"

    context = "\n".join(
        _format_hit_context_gemma(i + 1, hit) for i, hit in enumerate(hits[:max_hits])
    )
    raw = client.call(
        system=_ANSWER_SYSTEM,
        user=_ANSWER_USER_TMPL.format(query=query, context=context),
    )
    return GemmaLLMClient.clean_output(raw)


# ---------------------------------------------------------------------------
# Gemma3AnswerGenerator  (AnswerGenerator Protocol 구현)
# ---------------------------------------------------------------------------

class Gemma3AnswerGenerator:
    """
    3-stage pipeline (의도 분석 → VLM-aware 쿼리 확장 → 답변 생성).

    MemoryQueryService.chat() 이 호출하는 generate() 외에도,
    검색 전 단계(의도 분석 + 쿼리 확장)를 위해
    expand_query(query, records) 를 별도로 제공합니다.
    """

    def __init__(
        self,
        client: GemmaLLMClient,
        *,
        fallback_generator: TemplateAnswerGenerator | None = None,
        max_context_hits: int = MAX_CONTEXT_HITS,
    ) -> None:
        self.client = client
        self.fallback = fallback_generator or TemplateAnswerGenerator()
        self.max_context_hits = max(1, min(max_context_hits, 5))

    def expand_query(self, query: str, records: list[MemoryRecord]) -> str:
        """
        Stage 1 + Stage 2:
        사용자 질문 → 의도 분석 → VLM 컨텍스트 기반 쿼리 확장.
        반환값: 원본 질문 + 확장 키워드를 합친 augmented query string.
        """
        intent = _run_intent_analysis(self.client, query)
        expanded = _run_query_expansion(self.client, intent.target_object, records)
        if expanded:
            return query + " " + " ".join(expanded)
        return query

    def generate(self, query: str, hits: list[SearchHit]) -> GeneratedAnswer:
        """Stage 3: 검색 결과 기반 자연어 답변 생성."""
        if not hits:
            return self.fallback.generate(query, hits)

        cited_ids = [h.memory.memory_id for h in hits[: self.max_context_hits]]
        try:
            text = _run_answer_generation(self.client, query, hits, self.max_context_hits)
            return GeneratedAnswer(
                text=text,
                mode="gemma3_3stage",
                cited_memory_ids=cited_ids,
                confidence=round(max(0.55, min(hits[0].score + 0.2, 0.95)), 2),
                reason=(
                    f"Gemma3 3-stage pipeline: "
                    f"model={self.client.model}, hits={len(hits)}"
                ),
            )
        except Exception as exc:
            fallback = self.fallback.generate(query, hits)
            return GeneratedAnswer(
                text=fallback.text,
                mode=fallback.mode,
                cited_memory_ids=fallback.cited_memory_ids,
                confidence=fallback.confidence,
                reason=f"Gemma3 fallback: {exc}. {fallback.reason or ''}",
            )


# ---------------------------------------------------------------------------
# OllamaAnswerGenerator (레거시 호환, 단순 1-shot)
# ---------------------------------------------------------------------------

class OllamaAnswerGenerator:
    def __init__(
        self,
        client: OllamaChatClient,
        *,
        fallback_generator: TemplateAnswerGenerator | None = None,
        max_context_hits: int = MAX_CONTEXT_HITS,
    ) -> None:
        self.client = client
        self.fallback_generator = fallback_generator or TemplateAnswerGenerator()
        self.max_context_hits = max(1, min(max_context_hits, 5))

    def _format_hit_context(self, index: int, hit: SearchHit) -> str:
        memory = hit.memory
        location = memory.location.name or memory.location.address or "Unknown"
        captured_at = format_timestamp(memory.captured_at) or memory.captured_at or "Unknown"
        detected_objects = ", ".join(memory.detected_objects[:8]) or "None"
        tags = ", ".join(memory.tags[:8]) or "None"
        position_hint = memory.position_hint or "None"
        caption = memory.caption or "None"
        scene_summary = memory.scene_summary or "None"
        image_key = memory.image_key or "No image"

        return (
            f"[Memory {index}]\n"
            f"- Image Key: {image_key}\n"
            f"- Captured At: {captured_at}\n"
            f"- Location: {location}\n"
            f"- Position Hint: {position_hint}\n"
            f"- Detected Objects: {detected_objects}\n"
            f"- Tags: {tags}\n"
            f"- Caption: {caption}\n"
            f"- Scene Summary: {scene_summary}\n"
        )

    def _build_messages(self, query: str, hits: list[SearchHit]) -> list[dict[str, str]]:
        context = "\n".join(
            self._format_hit_context(index + 1, hit)
            for index, hit in enumerate(hits[: self.max_context_hits])
        )
        system_prompt = "You are a smart assistant that helps the user find their belongings. Always respond in Korean."
        user_prompt = (
            "Answer the question based on the provided [Observation Records] below. These records are sorted by recency and relevance.\n"
            "Note: Even if the item name the user is searching for does not exactly match the records, infer and treat them as the same item if they are conceptually similar, synonyms, or have a hypernym/hyponym relationship (e.g., 'wristwatch' and 'Apple Watch', 'earphones' and 'AirPods').\n"
            "If the requested item cannot be found or inferred from the records, you MUST reply exactly with: \"해당 물건은 최근 기록에서 찾을 수 없습니다.\"\n"
            "If the target item is found, you MUST output the observation time, location hints, and surrounding objects (features) along with the **original image key (image_key)**.\n\n"
            f"[Observation Records]\n{context}\n\n"
            f"[User Question]\n{query}"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def generate(self, query: str, hits: list[SearchHit]) -> GeneratedAnswer:
        if not hits:
            return self.fallback_generator.generate(query, hits)

        cited_memory_ids = [
            hit.memory.memory_id for hit in hits[: self.max_context_hits]
        ]
        try:
            answer_text = self.client.chat(messages=self._build_messages(query, hits))
            confidence = max(0.55, min(hits[0].score + 0.2, 0.95))
            return GeneratedAnswer(
                text=answer_text,
                mode="ollama",
                cited_memory_ids=cited_memory_ids,
                confidence=round(confidence, 2),
                reason=(
                    f"Ollama model {self.client.model} generated the answer "
                    "from retrieved memory context."
                ),
            )
        except Exception as exc:
            fallback = self.fallback_generator.generate(query, hits)
            return GeneratedAnswer(
                text=fallback.text,
                mode=fallback.mode,
                cited_memory_ids=fallback.cited_memory_ids,
                confidence=fallback.confidence,
                reason=(
                    f"Ollama fallback triggered: {exc}. "
                    f"{fallback.reason or 'Template answer was used.'}"
                ),
            )


    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout_sec: float = 20.0,
        http_client: ChatHttpClient | None = None,
    ) -> None:
        self.base_url = self._normalize_text(base_url)
        self.model = self._normalize_text(model)
        self.api_key = self._normalize_text(api_key) or None
        self.timeout_sec = max(5.0, float(timeout_sec))
        self.http_client = http_client or httpx

        if not self.base_url:
            raise ValueError("API_LLM_OLLAMA_BASE_URL is required")
        if not self.model:
            raise ValueError("API_LLM_OLLAMA_MODEL is required")
        if self.base_url.startswith("https://ollama.com") and not self.api_key:
            raise ValueError("API_LLM_OLLAMA_API_KEY is required for Ollama cloud")

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None:
            return ""
        return " ".join(str(value).strip().split())

    def chat(self, *, messages: list[dict[str, str]]) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        response = self.http_client.post(
            f"{self.base_url.rstrip('/')}/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
            },
            headers=headers,
            timeout=self.timeout_sec,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Ollama chat response is invalid")

        message = payload.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("Ollama chat response is missing message")

        content = self._normalize_text(message.get("content"))
        if not content:
            raise RuntimeError("Ollama chat response is missing content")
        return content


class OllamaAnswerGenerator:
    def __init__(
        self,
        client: OllamaChatClient,
        *,
        fallback_generator: TemplateAnswerGenerator | None = None,
        max_context_hits: int = MAX_CONTEXT_HITS,
    ) -> None:
        self.client = client
        self.fallback_generator = fallback_generator or TemplateAnswerGenerator()
        self.max_context_hits = max(1, min(max_context_hits, 5))

    def _format_hit_context(self, index: int, hit: SearchHit) -> str:
        memory = hit.memory
        location = memory.location.name or memory.location.address or "Unknown"
        captured_at = format_timestamp(memory.captured_at) or memory.captured_at or "Unknown"
        detected_objects = ", ".join(memory.detected_objects[:8]) or "None"
        tags = ", ".join(memory.tags[:8]) or "None"
        position_hint = memory.position_hint or "None"
        caption = memory.caption or "None"
        scene_summary = memory.scene_summary or "None"
        image_key = memory.image_key or "No image"

        return (
            f"[Memory {index}]\n"
            f"- Image Key: {image_key}\n"
            f"- Captured At: {captured_at}\n"
            f"- Location: {location}\n"
            f"- Position Hint: {position_hint}\n"
            f"- Detected Objects: {detected_objects}\n"
            f"- Tags: {tags}\n"
            f"- Caption: {caption}\n"
            f"- Scene Summary: {scene_summary}\n"
        )

    def _build_messages(self, query: str, hits: list[SearchHit]) -> list[dict[str, str]]:
        context = "\n".join(
            self._format_hit_context(index + 1, hit)
            for index, hit in enumerate(hits[: self.max_context_hits])
        )
        system_prompt = "You are a smart assistant that helps the user find their belongings. Always respond in Korean."
        user_prompt = (
            "Answer the question based on the provided [Observation Records] below. These records are sorted by recency and relevance.\n"
            "Note: Even if the item name the user is searching for does not exactly match the records, infer and treat them as the same item if they are conceptually similar, synonyms, or have a hypernym/hyponym relationship (e.g., 'wristwatch' and 'Apple Watch', 'earphones' and 'AirPods').\n"
            "If the requested item cannot be found or inferred from the records, you MUST reply exactly with: \"해당 물건은 최근 기록에서 찾을 수 없습니다.\"\n"
            "If the target item is found, you MUST output the observation time, location hints, and surrounding objects (features) along with the **original image key (image_key)**.\n\n"
            f"[Observation Records]\n{context}\n\n"
            f"[User Question]\n{query}"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def generate(self, query: str, hits: list[SearchHit]) -> GeneratedAnswer:
        if not hits:
            return self.fallback_generator.generate(query, hits)

        cited_memory_ids = [
            hit.memory.memory_id for hit in hits[: self.max_context_hits]
        ]
        try:
            answer_text = self.client.chat(messages=self._build_messages(query, hits))
            confidence = max(0.55, min(hits[0].score + 0.2, 0.95))
            return GeneratedAnswer(
                text=answer_text,
                mode="ollama",
                cited_memory_ids=cited_memory_ids,
                confidence=round(confidence, 2),
                reason=(
                    f"Ollama model {self.client.model} generated the answer "
                    "from retrieved memory context."
                ),
            )
        except Exception as exc:
            fallback = self.fallback_generator.generate(query, hits)
            return GeneratedAnswer(
                text=fallback.text,
                mode=fallback.mode,
                cited_memory_ids=fallback.cited_memory_ids,
                confidence=fallback.confidence,
                reason=(
                    f"Ollama fallback triggered: {exc}. "
                    f"{fallback.reason or 'Template answer was used.'}"
                ),
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
        answer_generator: AnswerGenerator | None = None,
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

    def recent_memories(
        self,
        user_id: str,
        limit: int | None = None,
    ) -> list[MemoryRecord]:
        resolved_limit = limit if isinstance(limit, int) and limit > 0 else self.default_top_k
        return self.repository.list_by_user(user_id, limit=min(resolved_limit, 50))

    def chat(
        self,
        user_id: str,
        query: str,
        top_k: int | None = None,
    ) -> tuple[GeneratedAnswer, list[SearchHit]]:
        """
        3-stage 파이프라인 지원:
        - answer_generator가 Gemma3AnswerGenerator이면
          Stage1(의도 분석) + Stage2(쿼리 확장) 로 augmented query 를 먼저 생성,
          확장된 쿼리로 검색 후 Stage3(답변 생성) 진행.
        - 기타 제네레이터는 기존 쿼리 그대로 검색.
        """
        if isinstance(self.answer_generator, Gemma3AnswerGenerator):
            # Stage 1 + 2: 의도 분석 + VLM-aware 쿼리 확장
            # _search_hits 와 동일한 제한(max(top_k*10, 40))을 적용해 대용량 계정 타임아웃 방지
            resolved_top_k = top_k if isinstance(top_k, int) and top_k > 0 else self.default_top_k
            expansion_limit = max(resolved_top_k * 10, 40)
            expansion_records = self.repository.list_by_user(user_id, limit=expansion_limit)
            augmented_query = self.answer_generator.expand_query(query, expansion_records)
            hits = self.search(user_id, augmented_query, top_k)
        else:
            hits = self.search(user_id, query, top_k)
        # Stage 3 (또는 기존 generate)
        answer = self.answer_generator.generate(query, hits)
        return answer, hits

    def check_health(self) -> None:
        self.repository.check_health()


def build_default_memory_query_service() -> MemoryQueryService:
    database_url = os.getenv("API_CAPTURE_DATABASE_URL", "").strip()
    if not database_url:
        raise ValueError("API_CAPTURE_DATABASE_URL is required for memory queries")
    top_k_raw = os.getenv("API_MEMORY_DEFAULT_TOP_K", "5").strip() or "5"
    llm_provider = os.getenv("API_LLM_PROVIDER", "template").strip().lower() or "template"

    answer_generator: TemplateAnswerGenerator | Gemma3AnswerGenerator | OllamaAnswerGenerator
    answer_generator = TemplateAnswerGenerator()

    if llm_provider == "ollama":
        # Gemma3 3-stage pipeline이 기본
        answer_generator = Gemma3AnswerGenerator(
            GemmaLLMClient(
                base_url=os.getenv("API_LLM_OLLAMA_BASE_URL", "https://ollama.com/api"),
                model=os.getenv("API_LLM_OLLAMA_MODEL", "gemma3:4b-cloud"),
                api_key=os.getenv("API_LLM_OLLAMA_API_KEY"),
                timeout_sec=float(
                    os.getenv("API_LLM_OLLAMA_TIMEOUT_SEC", "60").strip() or "60"
                ),
            ),
            fallback_generator=TemplateAnswerGenerator(),
        )

    return MemoryQueryService(
        PostgresMemoryStoreClient(database_url),
        default_top_k=max(1, min(int(top_k_raw), 20)),
        answer_generator=answer_generator,
    )
