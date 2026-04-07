from pathlib import Path
import unittest

from src.ingestion.models import MemoryDocument, MemoryLocation
from src.llm.answering import OpenAICompatibleAnswerGenerator
from src.retriever.hybrid import SearchHit
from src.utils.config import Settings


def build_hit(memory_id: str) -> SearchHit:
    memory = MemoryDocument(
        memory_id=memory_id,
        user_id="user-1",
        image_key=f"captures/{memory_id}.jpg",
        image_url=None,
        captured_at="2026-04-06T12:00:00Z",
        caption="an umbrella is near the sofa",
        scene_summary="living room scene",
        detected_objects=["umbrella", "sofa"],
        tags=["umbrella"],
        ocr_text=None,
        note=None,
        position_hint="sofa beside",
        location=MemoryLocation(name="living room"),
    )
    return SearchHit(
        memory=memory,
        score=0.9,
        lexical_score=0.8,
        matched_terms=["umbrella"],
    )


class FakeProvider:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, str]] = []

    def generate(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        return self.response


class LlmCitationAlignmentTestCase(unittest.TestCase):
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

    def test_cited_memory_ids_match_prompt_context_limit(self) -> None:
        hits = [build_hit("mem-umbrella-01"), build_hit("mem-umbrella-02"), build_hit("mem-umbrella-03")]
        provider = FakeProvider("우산은 거실에 있습니다.")
        generator = OpenAICompatibleAnswerGenerator(self.settings, provider=provider)

        answer = generator.generate("우산 어디에?", hits)

        self.assertEqual(answer.mode, "llm")
        self.assertEqual(answer.cited_memory_ids, ["mem-umbrella-01", "mem-umbrella-02"])
        self.assertEqual(len(answer.cited_memory_ids), 2)
        self.assertEqual(len(provider.calls), 1)


if __name__ == "__main__":
    unittest.main()
