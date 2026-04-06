from pathlib import Path
import unittest

from src.ingestion.models import MemoryDocument, MemoryLocation
from src.llm.answering import OpenAICompatibleAnswerGenerator
from src.llm.prompts import build_system_prompt, build_user_prompt
from src.retriever.hybrid import SearchHit
from src.utils.config import Settings


def build_hit(
    *,
    memory_id: str,
    user_id: str,
    caption: str,
    detected_objects: list[str],
    tags: list[str],
    location_name: str,
    position_hint: str | None = None,
) -> SearchHit:
    memory = MemoryDocument(
        memory_id=memory_id,
        user_id=user_id,
        image_key=f"captures/{memory_id}.jpg",
        image_url=None,
        captured_at="2026-04-06T12:00:00Z",
        caption=caption,
        scene_summary="cafe table scene",
        detected_objects=detected_objects,
        tags=tags,
        ocr_text=None,
        note=None,
        position_hint=position_hint,
        location=MemoryLocation(name=location_name),
    )
    return SearchHit(
        memory=memory,
        score=0.92,
        lexical_score=0.71,
        matched_terms=["umbrella"],
    )


class FakeProvider:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


class LlmAnsweringTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(
            service_name="rag-service",
            storage_path=Path("memory_store.json"),
            default_top_k=5,
            llm_provider="ollama",
            llm_api_key="ollama",
            llm_base_url="http://localhost:11434/v1",
            llm_model="qwen2.5:3b",
            llm_timeout_sec=20.0,
        )

    def test_prompt_builder_includes_grounded_context(self) -> None:
        hit = build_hit(
            memory_id="mem-umbrella-01",
            user_id="user-1",
            caption="an umbrella is leaning against the sofa",
            detected_objects=["umbrella", "sofa"],
            tags=["umbrella", "living-room"],
            location_name="거실",
            position_hint="소파 옆",
        )

        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(query="우산 어디 있어?", hits=[hit])

        self.assertIn("Answer in Korean", system_prompt)
        self.assertIn("memory_id: mem-umbrella-01", user_prompt)
        self.assertIn("matched_terms: umbrella", user_prompt)
        self.assertIn("Question: 우산 어디 있어?", user_prompt)

    def test_generator_uses_provider_when_hits_exist(self) -> None:
        hit = build_hit(
            memory_id="mem-umbrella-01",
            user_id="user-1",
            caption="an umbrella is leaning against the sofa",
            detected_objects=["umbrella", "sofa"],
            tags=["umbrella", "living-room"],
            location_name="거실",
            position_hint="소파 옆",
        )
        provider = FakeProvider("우산은 소파 옆에 있습니다.")
        generator = OpenAICompatibleAnswerGenerator(self.settings, provider=provider)

        answer = generator.generate("우산 어디 있어?", [hit])

        self.assertEqual(answer.mode, "llm")
        self.assertEqual(answer.text, "우산은 소파 옆에 있습니다.")
        self.assertEqual(answer.cited_memory_ids, ["mem-umbrella-01"])
        self.assertEqual(answer.confidence, 0.8)
        self.assertEqual(len(provider.calls), 1)
        self.assertIn("Answer in Korean", provider.calls[0][0])
        self.assertIn("Question: 우산 어디 있어?", provider.calls[0][1])

    def test_generator_falls_back_without_hits(self) -> None:
        provider = FakeProvider("should not be used")
        generator = OpenAICompatibleAnswerGenerator(self.settings, provider=provider)

        answer = generator.generate("우산 어디 있어?", [])

        self.assertEqual(answer.mode, "template")
        self.assertEqual(provider.calls, [])


if __name__ == "__main__":
    unittest.main()
