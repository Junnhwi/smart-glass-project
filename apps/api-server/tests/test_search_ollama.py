from __future__ import annotations

import unittest

from src.database.memory_store import MemoryLocation, MemoryRecord
from src.modules.search.service import (
    OllamaAnswerGenerator,
    OllamaChatClient,
    SearchHit,
    TemplateAnswerGenerator,
)


class FakeHttpResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeHttpClient:
    def __init__(self, payload):
        self.payload = payload
        self.last_url = None
        self.last_json = None
        self.last_headers = None
        self.last_timeout = None

    def post(self, url, *args, **kwargs):
        self.last_url = url
        self.last_json = kwargs.get("json")
        self.last_headers = kwargs.get("headers")
        self.last_timeout = kwargs.get("timeout")
        return FakeHttpResponse(self.payload)


class RaisingOllamaClient:
    def chat(self, *, messages):
        raise RuntimeError("ollama unavailable")


def make_hit(memory_id: str = "mem-001") -> SearchHit:
    return SearchHit(
        memory=MemoryRecord(
            memory_id=memory_id,
            user_id="user-1",
            image_key="captures/user-1/sample.jpg",
            image_url=None,
            captured_at="2026-05-07T04:00:00Z",
            caption="wallet on the desk next to the laptop",
            scene_summary="workspace desk scene",
            detected_objects=["wallet", "desk", "laptop"],
            tags=["workspace"],
            ocr_text=None,
            note=None,
            position_hint="next to laptop",
            location=MemoryLocation(name="workspace"),
        ),
        score=0.73,
        lexical_score=0.73,
        matched_terms=["wallet"],
    )


class OllamaChatClientTests(unittest.TestCase):
    def test_chat_posts_to_ollama_cloud_endpoint_with_auth_header(self) -> None:
        http_client = FakeHttpClient({"message": {"content": "지갑은 책상 위에 있어요."}})
        client = OllamaChatClient(
            base_url="https://ollama.com/api",
            model="gpt-oss:20b-cloud",
            api_key="test-key",
            http_client=http_client,
        )

        answer = client.chat(messages=[{"role": "user", "content": "지갑 어디 있어?"}])

        self.assertEqual(answer, "지갑은 책상 위에 있어요.")
        self.assertEqual(http_client.last_url, "https://ollama.com/api/chat")
        self.assertEqual(http_client.last_json["model"], "gpt-oss:20b-cloud")
        self.assertFalse(http_client.last_json["stream"])
        self.assertEqual(http_client.last_headers["Authorization"], "Bearer test-key")

    def test_cloud_client_requires_api_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "API_LLM_OLLAMA_API_KEY is required"):
            OllamaChatClient(
                base_url="https://ollama.com/api",
                model="gpt-oss:20b-cloud",
            )


class OllamaAnswerGeneratorTests(unittest.TestCase):
    def test_generate_returns_ollama_answer_when_call_succeeds(self) -> None:
        http_client = FakeHttpClient({"message": {"content": "지갑은 작업실 책상 노트북 옆에 있었어요."}})
        client = OllamaChatClient(
            base_url="https://ollama.com/api",
            model="gpt-oss:20b-cloud",
            api_key="test-key",
            http_client=http_client,
        )
        generator = OllamaAnswerGenerator(client)

        answer = generator.generate("내 지갑 어디 있었지?", [make_hit()])

        self.assertEqual(answer.mode, "ollama")
        self.assertEqual(answer.cited_memory_ids, ["mem-001"])
        self.assertIn("지갑은 작업실 책상", answer.text)
        self.assertIn("마지막 확인 시각은 2026-05-07 오후 1시입니다.", answer.text)
        self.assertIn("gpt-oss:20b-cloud", answer.reason or "")
        messages = http_client.last_json["messages"]
        self.assertIn("2026-05-07 오후 1시", messages[-1]["content"])
        self.assertIn("KST", messages[-1]["content"])

    def test_generate_falls_back_when_ollama_claims_not_found_despite_hits(self) -> None:
        http_client = FakeHttpClient(
            {"message": {"content": "해당 물건은 최근 기록에서 찾을 수 없습니다."}}
        )
        client = OllamaChatClient(
            base_url="https://ollama.com/api",
            model="gpt-oss:20b-cloud",
            api_key="test-key",
            http_client=http_client,
        )
        generator = OllamaAnswerGenerator(client)

        answer = generator.generate("내 물병 어디 있었지?", [make_hit()])

        self.assertEqual(answer.mode, "template")
        self.assertEqual(answer.cited_memory_ids, ["mem-001"])
        self.assertIn("마지막 확인 시각은 2026-05-07 오후 1시입니다.", answer.text)
        self.assertIn("claimed no matching record", answer.reason or "")

    def test_generate_falls_back_to_template_when_ollama_fails(self) -> None:
        generator = OllamaAnswerGenerator(
            RaisingOllamaClient(),  # type: ignore[arg-type]
            fallback_generator=TemplateAnswerGenerator(),
        )

        answer = generator.generate("내 지갑 어디 있었지?", [make_hit("mem-002")])

        self.assertEqual(answer.mode, "template")
        self.assertEqual(answer.cited_memory_ids, ["mem-002"])
        self.assertIn("마지막 확인 시각", answer.text)
        self.assertIn("Ollama fallback triggered", answer.reason or "")


if __name__ == "__main__":
    unittest.main()
