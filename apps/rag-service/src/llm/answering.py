from __future__ import annotations

from dataclasses import dataclass, field

from src.core.logging import get_logger
from src.llm.prompts import build_system_prompt, build_user_prompt
from src.llm.providers import LLMProvider, OpenAICompatibleProvider
from src.retriever.hybrid import SearchHit
from src.utils.config import Settings
from src.utils.text import format_timestamp


logger = get_logger(__name__)


@dataclass(slots=True)
class GeneratedAnswer:
    text: str
    mode: str
    cited_memory_ids: list[str] = field(default_factory=list)
    confidence: float | None = None
    reason: str | None = None


class TemplateAnswerGenerator:
    def _describe_location(self, hit: SearchHit) -> str:
        memory = hit.memory
        details: list[str] = []

        if memory.location.name:
            details.append(f"\uc704\uce58: {memory.location.name}")
        elif memory.location.address:
            details.append(f"\uc704\uce58: {memory.location.address}")

        if memory.position_hint:
            details.append(f"\uc0c1\ub300 \uc704\uce58: {memory.position_hint}")
        elif memory.caption:
            details.append(f"\uc124\uba85: {memory.caption}")

        formatted_time = format_timestamp(memory.captured_at)
        if formatted_time:
            details.append(f"\ucd2c\uc601 \uc2dc\uac01: {formatted_time}")

        if not details:
            return "\uc704\uce58 \ub2e8\uc11c\ub97c \ucc3e\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4."

        return ", ".join(details)

    def generate(self, query: str, hits: list[SearchHit]) -> GeneratedAnswer:
        if not hits:
            return GeneratedAnswer(
                text=(
                    "\uad00\ub828 \uba54\ubaa8\ub9ac\ub97c \ucc3e\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4. "
                    "\uc9c8\ubb38\uc744 \ub354 \uad6c\uccb4\uc801\uc73c\ub85c \ub9d0\ud574 \uc8fc\uc138\uc694."
                ),
                mode="template",
                cited_memory_ids=[],
                confidence=None,
                reason="\uac80\uc0c9 \uacb0\uacfc\uac00 \uc5c6\uc5b4\uc11c \ud15c\ud50c\ub9bf \uc751\ub2f5\uc744 \uc0ac\uc6a9\ud588\uc2b5\ub2c8\ub2e4.",
            )

        top_hit = hits[0]
        top_memory = top_hit.memory
        answer_parts = [
            f"\uac00\uc7a5 \uad00\ub828 \uc788\ub294 \uba54\ubaa8\ub9ac\ub294 {top_memory.memory_id}\uc785\ub2c8\ub2e4.",
            self._describe_location(top_hit),
        ]

        if len(hits) > 1:
            alternative_ids = ", ".join(hit.memory.memory_id for hit in hits[1:3])
            answer_parts.append(f"\ucd94\uac00 \ud6c4\ubcf4: {alternative_ids}")

        return GeneratedAnswer(
            text=" ".join(answer_parts),
            mode="template",
            cited_memory_ids=[hit.memory.memory_id for hit in hits[:3]],
            confidence=0.5,
            reason="\uac80\uc0c9 \uacb0\uacfc\ub97c \uae30\ubc18\uc73c\ub85c \ud15c\ud50c\ub9bf \uc751\ub2f5\uc744 \uc0ac\uc6a9\ud588\uc2b5\ub2c8\ub2e4.",
        )


class OpenAICompatibleAnswerGenerator:
    def __init__(
        self,
        settings: Settings,
        provider: LLMProvider | None = None,
    ) -> None:
        self.settings = settings
        self.provider = provider if provider is not None else self._build_provider()
        self.fallback = TemplateAnswerGenerator()

    def _build_provider(self) -> LLMProvider | None:
        if self.settings.llm_provider == "template":
            return None
        if not self.settings.llm_enabled:
            return None
        if self.settings.llm_provider not in {"auto", "ollama", "openai"}:
            return None

        return OpenAICompatibleProvider(
            api_key=self.settings.llm_api_key,
            model=self.settings.llm_model,
            base_url=self.settings.llm_base_url,
            timeout_sec=self.settings.llm_timeout_sec,
        )

    def generate(self, query: str, hits: list[SearchHit]) -> GeneratedAnswer:
        if not hits:
            return self.fallback.generate(query, hits)

        if self.provider is None:
            return self.fallback.generate(query, hits)

        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(query=query, hits=hits)

        try:
            content = self.provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
            if isinstance(content, str) and content.strip():
                return GeneratedAnswer(
                    text=content.strip(),
                    mode="llm",
                    cited_memory_ids=[hit.memory.memory_id for hit in hits[:3]],
                    confidence=0.8,
                    reason="\uac80\uc0c9 \uadfc\uac70\ub97c \ubc14\ud0d5\uc73c\ub85c \ub2f5\ubcc0\uc744 \uc0dd\uc131\ud588\uc2b5\ub2c8\ub2e4.",
                )
        except Exception:
            logger.exception("LLM answer generation failed")

        return self.fallback.generate(query, hits)
