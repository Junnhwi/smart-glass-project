from dataclasses import dataclass

from src.core.logging import get_logger
from src.retriever.hybrid import SearchHit
from src.utils.config import Settings
from src.utils.text import format_timestamp


logger = get_logger(__name__)

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - import failure is handled via fallback
    OpenAI = None


@dataclass(slots=True)
class GeneratedAnswer:
    text: str
    mode: str


def _describe_location(hit: SearchHit) -> str:
    memory = hit.memory
    details: list[str] = []

    if memory.location.name:
        details.append(f"위치 태그는 {memory.location.name}")
    elif memory.location.address:
        details.append(f"위치 태그는 {memory.location.address}")

    if memory.position_hint:
        details.append(f"사진 단서로는 {memory.position_hint}")
    elif memory.caption:
        details.append(f"사진 설명은 '{memory.caption}'")

    formatted_time = format_timestamp(memory.captured_at)
    if formatted_time:
        details.append(f"촬영 시각은 {formatted_time}")

    if not details:
        return "위치 단서는 부족하지만 해당 사진이 가장 유력합니다."

    return ", ".join(details) + "입니다."


class TemplateAnswerGenerator:
    def generate(self, query: str, hits: list[SearchHit]) -> GeneratedAnswer:
        if not hits:
            return GeneratedAnswer(
                text=(
                    "저장된 기억에서 질문과 직접 연결되는 사진을 찾지 못했어요. "
                    "물건 이름이나 장소 단서를 조금 더 넣어서 다시 물어보면 더 잘 찾을 수 있습니다."
                ),
                mode="template",
            )

        top_hit = hits[0]
        top_memory = top_hit.memory
        answer_parts = [
            f"가장 가능성이 높은 기록은 메모리 {top_memory.memory_id} 입니다.",
            _describe_location(top_hit),
        ]

        if len(hits) > 1:
            alternative_ids = ", ".join(hit.memory.memory_id for hit in hits[1:3])
            answer_parts.append(f"비슷한 후보로는 {alternative_ids}도 함께 확인해 보세요.")

        return GeneratedAnswer(text=" ".join(answer_parts), mode="template")


class OpenAICompatibleAnswerGenerator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.fallback = TemplateAnswerGenerator()

    def generate(self, query: str, hits: list[SearchHit]) -> GeneratedAnswer:
        if not self.settings.llm_enabled or OpenAI is None:
            return self.fallback.generate(query, hits)

        if not hits:
            return self.fallback.generate(query, hits)

        client = OpenAI(
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            timeout=self.settings.llm_timeout_sec,
        )

        context_lines: list[str] = []
        for hit in hits[:5]:
            memory = hit.memory
            context_lines.append(
                "\n".join(
                    [
                        f"memory_id: {memory.memory_id}",
                        f"score: {hit.score}",
                        f"captured_at: {memory.captured_at or ''}",
                        f"location_name: {memory.location.name or ''}",
                        f"location_address: {memory.location.address or ''}",
                        f"position_hint: {memory.position_hint or ''}",
                        f"caption: {memory.caption or ''}",
                        f"scene_summary: {memory.scene_summary or ''}",
                        f"detected_objects: {', '.join(memory.detected_objects)}",
                        f"matched_terms: {', '.join(hit.matched_terms)}",
                    ]
                )
            )

        system_prompt = (
            "You are a smart-glass memory assistant. "
            "Answer in Korean. "
            "Use only the provided memory context. "
            "If the context is weak, clearly say it is uncertain. "
            "Mention the best memory_id and location clue."
        )
        user_prompt = (
            f"사용자 질문: {query}\n\n"
            "검색된 메모리 후보:\n"
            f"{chr(10).join(context_lines)}"
        )

        try:
            response = client.chat.completions.create(
                model=self.settings.llm_model,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
            content = response.choices[0].message.content
            if isinstance(content, str) and content.strip():
                return GeneratedAnswer(text=content.strip(), mode="llm")
        except Exception:
            logger.exception("LLM answer generation failed")

        return self.fallback.generate(query, hits)
