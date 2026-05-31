from __future__ import annotations

"""run_llm_search_service.py

3-stage LLM pipeline test for the Smart Glass memory search:
  Stage 1 – Intent Analysis   (의도 파악: 무엇을 찾고 있는가?)
  Stage 2 – Query Expansion   (쿼리 확장: 동의어/상위어/제품명 + VLM 실제 데이터 기반 확장)
  Stage 3 – Answer Generation (최종 답변 생성: 자연스러운 한국어)

Model: Gemma3 (via Ollama)
Prompts are structured with Gemma3 best-practices in mind:
  Role → Instruction → Context → Query 계층 구조 사용
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
AI_TEST_DIR = Path(__file__).resolve().parent
API_SRC_DIR = ROOT_DIR / "apps" / "api-server"
DEFAULT_VLM_RESULT_PATH = AI_TEST_DIR / "vlm_result.json"
DEFAULT_OUTPUT_PATH = AI_TEST_DIR / "llm_search_result.json"
DEFAULT_USER_QUESTION = "에어팟 어디 있어?"
DEFAULT_LLM_MODEL = "gemma3:4b-cloud"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _env_value(key: str, default: str = "") -> str:
    dotenv_values = _load_dotenv(ROOT_DIR / ".env")
    return (os.getenv(key) or dotenv_values.get(key) or default).strip()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# In-memory memory repository (reads worker JSON)
# ---------------------------------------------------------------------------

class JsonMemoryRepository:
    def __init__(self, records: list[Any]) -> None:
        self.records = records

    def list_by_user(self, user_id: str, *, limit: int | None = None) -> list[Any]:
        matched = [r for r in self.records if r.user_id == user_id]
        matched.sort(
            key=lambda r: (r.captured_at or "", r.memory_id),
            reverse=True,
        )
        matched.sort(key=lambda r: r.captured_at is None)
        return matched[:limit] if limit else matched

    def check_health(self) -> None:
        return None


def _load_worker_results(path: Path) -> list[dict[str, Any]]:
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            return [payload]
        return []

    if path.is_dir():
        results: list[dict[str, Any]] = []
        for child in sorted(path.glob("*.json")):
            if child.name == DEFAULT_OUTPUT_PATH.name:
                continue
            try:
                payload = json.loads(child.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict) and payload.get("status") == "success":
                results.append(payload)
        return results

    raise FileNotFoundError(path)


def _schema_to_payload_dict(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=False)
    return payload.dict(exclude_none=False)


def _build_pipeline_output_map(worker_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    memory_record_from_vlm_result() 변환 시 pipelineOutput이 MemoryRecord에 저장되지 않는다.
    raw worker result JSON에서 memory_id → pipelineOutput 맵을 따로 유지해 Stage 2/3에서 활용.
    """
    result: dict[str, dict[str, Any]] = {}
    for item in worker_results:
        memory_id = (item.get("memoryId") or "").strip()
        pipeline_output = item.get("pipelineOutput")
        if memory_id and isinstance(pipeline_output, dict):
            result[memory_id] = pipeline_output
    return result


# ---------------------------------------------------------------------------
# Qwen-optimised Ollama client
# ---------------------------------------------------------------------------

@dataclass
class GemmaOllamaClient:
    """
    Wraps the Ollama /api/chat endpoint with Gemma3 best-practices:
    - Explicit system / user role separation (Gemma3 honours system role via Ollama)
    - temperature=0.3 for grounded RAG responses (lower than Qwen default)
    - repeat_penalty=1.0 (Gemma3 rarely repeats; over-penalising degrades quality)
    - Strips markdown artefacts (**, ##, ---, bullet formatting) from responses
    """

    base_url: str
    model: str
    api_key: str | None = None
    timeout_sec: float = 60.0

    def _post(self, messages: list[dict[str, str]]) -> str:
        import httpx

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        url = f"{self.base_url.rstrip('/')}/chat"
        body = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                # Gemma3 best-practice: lower temp for grounded RAG answers
                "temperature": 0.3,
                # Gemma3 does not need heavy repetition penalty
                "repeat_penalty": 1.0,
                # Ensure enough context window for long VLM records
                "num_ctx": 4096,
            },
        }

        try:
            resp = httpx.post(url, json=body, headers=headers, timeout=self.timeout_sec)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"LLM API error {exc.response.status_code} at {url}: "
                f"{exc.response.text[:300]}"
            ) from exc

        data = resp.json()
        content: str = data.get("message", {}).get("content", "").strip()
        return content

    def call(self, *, system: str, user: str) -> str:
        """Single-turn call with an explicit system prompt."""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        return self._post(messages)

    @staticmethod
    def clean_llm_output(text: str) -> str:
        """
        Remove common LLM formatting artefacts so the answer reads naturally:
          **bold**  →  plain text
          ## heading  →  removed
          leading bullets (-, *, •)  →  removed
          trailing 'image_key: ...'  →  removed
        """
        import re

        # Remove bold/italic markdown
        text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
        # Remove heading markers
        text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
        # Remove leading list markers
        text = re.sub(r"^[\-\*•]\s+", "", text, flags=re.MULTILINE)
        # Remove image_key mentions (internal system artefact)
        text = re.sub(r"\(?image_key\s*:\s*\S+\)?", "", text, flags=re.IGNORECASE)
        # Collapse extra whitespace / blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()


# ---------------------------------------------------------------------------
# Stage 1 – Intent Analysis
# ---------------------------------------------------------------------------

@dataclass
class IntentResult:
    target_object: str          # 찾고 있는 사물 (정제된 핵심 명사)
    intent_summary: str         # 의도 요약 (한 문장)
    raw: str = ""               # LLM 원문 응답


# Gemma3 best-practice: Korean system prompt + Role→Instruction→Output format
INTENT_SYSTEM = """\
[역할]
당신은 스마트 글라스 기억 보조 시스템의 의도 분석 모듈입니다.
사용자 발화에서 찾고 있는 핵심 사물(명사)을 추출하는 것이 유일한 임무입니다.

[출력 규칙]
- 반드시 아래 형식의 JSON 하나만 출력하세요. 설명이나 마크다운은 절대 포함하지 마세요.
- {"target_object": "<한국어 명사>", "intent_summary": "<한 문장 한국어 요약>"}
- target_object: 브랜드명은 그대로 유지하세요 (예: 에어팟, 애플워치, 갤럭시버즈).
- intent_summary: 사용자가 무엇을 원하는지 한 문장으로 설명하세요.
"""

INTENT_USER_TMPL = """\
[사용자 발화]
"{query}"
"""


def stage1_intent_analysis(client: "GemmaOllamaClient", query: str) -> IntentResult:
    raw = client.call(system=INTENT_SYSTEM, user=INTENT_USER_TMPL.format(query=query))

    # Attempt to parse JSON; fall back gracefully
    import re
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            return IntentResult(
                target_object=parsed.get("target_object", query).strip(),
                intent_summary=parsed.get("intent_summary", "").strip(),
                raw=raw,
            )
        except json.JSONDecodeError:
            pass

    return IntentResult(target_object=query.strip(), intent_summary="", raw=raw)


# ---------------------------------------------------------------------------
# Stage 2 – Query Expansion
# ---------------------------------------------------------------------------

@dataclass
class QueryExpansionResult:
    expanded_terms: list[str]   # 확장된 검색 키워드 목록
    raw: str = ""


# Gemma3 best-practice: explicit Role→Instruction→Context→Query structure in Korean
EXPANSION_SYSTEM = """\
[역할]
당신은 한국어 사물 검색 시스템의 쿼리 확장 모듈입니다.

[지침]
- 사용자가 찾는 사물명과 VLM(시각 AI)이 실제로 촬영된 장면에서 교배한 모든 정보(사물, 태그, 장만 요약, 위치 힌트, 장소)를 모두 참고하여
  검색에 활용할 수 있는 유사어·브랜드명·상위어·하위어 목록을 생성하세요.
- 반드시 아래 형식의 JSON 하나만 출력하세요. JSON 외 텍스트는 절대 포함하지 마세요.
- {"expanded_terms": ["term1", "term2", ...]}
- VLM이 감지한 사물 중 찾는 사물과 의미적으로 관련 있는 항목도 포함하세요.
- 실제 현장에 있는 사물명은 원문 그대로 포함하세요.
- 최대 14개 이내로 작성하세요.
"""

EXPANSION_USER_TMPL = """\
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


def _build_vlm_context_for_expansion(records: list[Any], pipeline_map: dict[str, Any]) -> dict[str, str]:
    """
    Stage 2 확장에 젬 모든 VLM 필드를 모아 반환.
    사용: detected_objects, tags, pipeline objects, caption, scene_summary, position_hint, location
    """
    all_objects: list[str] = []
    all_tags: list[str] = []
    captions: list[str] = []
    summaries: list[str] = []
    position_hints: list[str] = []
    locations: list[str] = []

    for rec in records:
        if rec.detected_objects:
            all_objects.extend(rec.detected_objects)
        if rec.tags:
            all_tags.extend(rec.tags)
        if rec.caption:
            captions.append(rec.caption)
        if rec.scene_summary:
            summaries.append(rec.scene_summary)
        if rec.position_hint:
            position_hints.append(rec.position_hint)
        loc = rec.location
        if loc.name:
            locations.append(loc.name)
        elif loc.address:
            locations.append(loc.address)
        # pipelineOutput.objects 내 사물명 추가
        po = pipeline_map.get(rec.memory_id, {})
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
        "vlm_position": _dedup(position_hints),
        "vlm_location": _dedup(locations),
    }


def stage2_query_expansion(
    client: "GemmaOllamaClient",
    target_object: str,
    records: list[Any],
    pipeline_map: dict[str, Any],
) -> QueryExpansionResult:
    ctx = _build_vlm_context_for_expansion(records, pipeline_map)
    raw = client.call(
        system=EXPANSION_SYSTEM,
        user=EXPANSION_USER_TMPL.format(
            target_object=target_object,
            **ctx,
        ),
    )

    import re
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            terms = parsed.get("expanded_terms", [])
            if isinstance(terms, list):
                return QueryExpansionResult(
                    expanded_terms=[str(t).strip() for t in terms if str(t).strip()],
                    raw=raw,
                )
        except json.JSONDecodeError:
            pass

    # Graceful fallback
    return QueryExpansionResult(expanded_terms=[target_object], raw=raw)


# ---------------------------------------------------------------------------
# Stage 3 – Answer Generation (Gemma3-optimised)
# ---------------------------------------------------------------------------

# Gemma3 best-practice: Role→Instruction→Context→Query, 한국어 지침으로 일관성 유지
ANSWER_SYSTEM = """\
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

ANSWER_USER_TMPL = """\
[사용자 질문]
{query}

[검색된 기억 기록 (최신순)]
{context}

위 기록만을 근거로 사용자의 질문에 자연스럽게 답변하세요.
기록에 찾는 사물이 없으면 "기록을 찾지 못했다"고 솔직하게 말하고 다른 이름으로 다시 물어보라고 안내하세요.
"""


def _format_hit_context(index: int, hit: Any, memory: Any, pipeline_map: dict[str, Any]) -> str:
    """MemoryRecord + pipelineOutput map 사용해 가능한 모든 VLM 필드 활용."""
    from src.modules.search.text import format_timestamp

    captured_str = format_timestamp(memory.captured_at) or memory.captured_at or "알 수 없음"
    scene = memory.scene_summary or memory.caption or "알 수 없음"
    position = memory.position_hint or "알 수 없음"
    objects_str = ", ".join(memory.detected_objects[:10]) if memory.detected_objects else "없음"

    # location (name / address)
    loc = memory.location
    location_str = loc.name or loc.address or "정보 없음"

    # ocr_text (이미지 내 텍스트)
    ocr_str = memory.ocr_text or ""

    # note (사용자 메모)
    note_str = memory.note or ""

    # pipelineOutput per-object detail (pipeline_map 활용)
    pipeline_detail = ""
    po = pipeline_map.get(memory.memory_id, {})
    obj_lines: list[str] = []
    for obj in po.get("objects", []):
        name = obj.get("name", "")
        pos = obj.get("position", {})
        hint = pos.get("hint", "")
        surface = pos.get("surface", "")
        nearby = ", ".join(obj.get("nearby_objects", []))
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


def stage3_answer_generation(
    client: "GemmaOllamaClient",
    query: str,
    hits: list[Any],
    pipeline_map: dict[str, Any],
    max_hits: int = 3,
) -> str:
    if not hits:
        return "해당 물건에 대한 최근 기록을 찾지 못했어요. 다른 이름이나 설명으로 다시 물어봐 주시겠어요?"

    context_parts = [
        _format_hit_context(i + 1, hit, hit.memory, pipeline_map)
        for i, hit in enumerate(hits[:max_hits])
    ]
    context = "\n".join(context_parts)

    raw = client.call(
        system=ANSWER_SYSTEM,
        user=ANSWER_USER_TMPL.format(query=query, context=context),
    )
    return GemmaOllamaClient.clean_llm_output(raw)


# ---------------------------------------------------------------------------
# Lexical search with expanded terms
# ---------------------------------------------------------------------------

def _lexical_search_with_expanded_terms(
    service: Any,
    user_id: str,
    original_query: str,
    expanded_terms: list[str],
    top_k: int,
) -> list[Any]:
    """
    Run the existing MemoryQueryService search, but augment its internal
    query string with the LLM-expanded terms so the lexical scorer can
    also match brand/synonym terms the static SYNONYM_GROUPS may not cover.
    """
    # Combine original query + expanded terms into one rich query string
    augmented_query = original_query + " " + " ".join(expanded_terms)
    return service.search(user_id, augmented_query, top_k)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "3-stage LLM pipeline (Intent → Expansion → Answer) "
            "using Gemma3 against VLM JSON results from ai_test2."
        )
    )
    parser.add_argument("--vlm-result", type=Path, default=DEFAULT_VLM_RESULT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--question", default=DEFAULT_USER_QUESTION)
    parser.add_argument("--user-id", default="")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument(
        "--base-url",
        default=_env_value("API_LLM_OLLAMA_BASE_URL", "http://127.0.0.1:11434/api"),
    )
    parser.add_argument(
        "--model",
        default=_env_value("OLLAMA_LLM_MODEL", DEFAULT_LLM_MODEL),
    )
    parser.add_argument("--api-key", default=_env_value("API_LLM_OLLAMA_API_KEY"))
    parser.add_argument(
        "--timeout-sec",
        type=float,
        default=float(_env_value("API_LLM_OLLAMA_TIMEOUT_SEC", "60") or "60"),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print intent + expansion results only; skip answer generation.",
    )
    parser.add_argument(
        "--skip-expansion",
        action="store_true",
        help="Skip Stage 2 LLM expansion; use only built-in SYNONYM_GROUPS.",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(API_SRC_DIR))

    from src.database.memory_store import memory_record_from_vlm_result
    from src.api.schemas import (
        MemoryChatResponse,
        MemoryLocationPayload,
        MemorySearchHitPayload,
    )
    from src.modules.search.service import (
        MemoryQueryService,
        TemplateAnswerGenerator,
    )

    # --- Load VLM results ------------------------------------------------
    worker_results = _load_worker_results(args.vlm_result)
    records = [memory_record_from_vlm_result(item) for item in worker_results]
    if not records:
        raise SystemExit(f"No successful VLM result JSON found at {args.vlm_result}")

    user_id = args.user_id or records[0].user_id
    # pipeline_map: memory_id → pipelineOutput (MemoryRecord에서 유실되는 데이터 복원)
    pipeline_map = _build_pipeline_output_map(worker_results)
    repository = JsonMemoryRepository(records)

    # MemoryQueryService with template fallback only (we handle LLM ourselves)
    service = MemoryQueryService(
        repository,
        default_top_k=args.top_k,
        answer_generator=TemplateAnswerGenerator(),
    )

    # --- Gemma3 client ---------------------------------------------------
    client = GemmaOllamaClient(
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key or None,
        timeout_sec=args.timeout_sec,
    )

    print(f"\n{'='*60}")
    print(f"  질문: {args.question}")
    print(f"  모델: {args.model}  |  base_url: {args.base_url}")
    print(f"{'='*60}\n")

    # ─────────────────────────────────────────────────────────
    # STAGE 1: Intent Analysis
    # ─────────────────────────────────────────────────────────
    print("[Stage 1] 의도 분석 중...")
    intent = stage1_intent_analysis(client, args.question)
    print(f"  → 검색 대상: {intent.target_object}")
    print(f"  → 의도 요약: {intent.intent_summary}")

    # ─────────────────────────────────────────────────────────
    # STAGE 2: Query Expansion
    # ─────────────────────────────────────────────────────────
    if args.skip_expansion:
        expansion = QueryExpansionResult(expanded_terms=[intent.target_object])
        print("\n[Stage 2] 확장 건너뜀 (--skip-expansion)")
    else:
        print("\n[Stage 2] 쿼리 확장 중... (VLM 실제 데이터 포함)")
        expansion = stage2_query_expansion(client, intent.target_object, records, pipeline_map)
        print(f"  → 확장 키워드: {expansion.expanded_terms}")

    if args.dry_run:
        print("\n[dry-run] 여기서 종료합니다.")
        print(json.dumps(
            {
                "intent": {
                    "target_object": intent.target_object,
                    "intent_summary": intent.intent_summary,
                },
                "expansion": {"expanded_terms": expansion.expanded_terms},
            },
            ensure_ascii=False,
            indent=2,
        ))
        return

    # ─────────────────────────────────────────────────────────
    # Lexical search (augmented with expanded terms)
    # ─────────────────────────────────────────────────────────
    print("\n[Search] 메모리 검색 중...")
    hits = _lexical_search_with_expanded_terms(
        service, user_id, args.question, expansion.expanded_terms, args.top_k
    )
    print(f"  → 검색 결과: {len(hits)}건 매칭")

    # ─────────────────────────────────────────────────────────
    # STAGE 3: Answer Generation
    # ─────────────────────────────────────────────────────────
    print("\n[Stage 3] 답변 생성 중...")
    answer_text = stage3_answer_generation(client, args.question, hits, pipeline_map)
    print(f"\n{'─'*60}")
    print(f"최종 답변:\n{answer_text}")
    print(f"{'─'*60}\n")

    # ─────────────────────────────────────────────────────────
    # Save output
    # ─────────────────────────────────────────────────────────
    output = _schema_to_payload_dict(
        MemoryChatResponse(
            answer=answer_text,
            answerMode="gemma3_3stage",
            query=args.question,
            totalHits=len(hits),
            hits=[
                MemorySearchHitPayload(
                    memoryId=hit.memory.memory_id,
                    score=hit.score,
                    lexicalScore=hit.lexical_score,
                    matchedTerms=hit.matched_terms,
                    imageKey=hit.memory.image_key,
                    imageUrl=hit.memory.image_url,
                    capturedAt=hit.memory.captured_at,
                    caption=hit.memory.caption,
                    sceneSummary=hit.memory.scene_summary,
                    positionHint=hit.memory.position_hint,
                    location=MemoryLocationPayload(**hit.memory.location.to_dict()),
                    detectedObjects=hit.memory.detected_objects,
                    tags=hit.memory.tags,
                )
                for hit in hits
            ],
            citedMemoryIds=[hit.memory.memory_id for hit in hits],
            confidence=round(max((hit.score for hit in hits), default=0.0), 2),
            reason=(
                f"Qwen 3-stage pipeline: intent={intent.target_object}, "
                f"expanded_terms={len(expansion.expanded_terms)}, hits={len(hits)}"
            ),
        )
    )

    # Inject pipeline metadata for debugging
    output["_pipeline"] = {
        "stage1_intent": {
            "target_object": intent.target_object,
            "intent_summary": intent.intent_summary,
        },
        "stage2_expansion": {"expanded_terms": expansion.expanded_terms},
        "model": args.model,
    }

    _write_json(args.output, output)
    print(f"결과 저장: {args.output}")


if __name__ == "__main__":
    main()
