import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from src.api.main import create_app


WORKROOM = "\uC791\uC5C5\uBC29"
ENTRYWAY = "\uD604\uAD00"
LIVING_ROOM = "\uAC70\uC2E4"
WALLET_QUERY = "\uB0B4 \uC9C0\uAC11 \uC5B4\uB514\uC5D0 \uC788\uC5C8\uC9C0?"
UMBRELLA_QUERY = "\uC6B0\uC0B0 \uC5B4\uB514 \uC788\uC5C8\uC5B4?"


class RagServiceApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["RAG_STORAGE_PATH"] = os.path.join(
            self.temp_dir.name,
            "memory_store.json",
        )
        os.environ.pop("LLM_API_KEY", None)
        os.environ.pop("LLM_MODEL", None)
        os.environ.pop("LLM_BASE_URL", None)
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        self.temp_dir.cleanup()
        os.environ.pop("RAG_STORAGE_PATH", None)

    def test_health_endpoint_returns_request_id(self) -> None:
        response = self.client.get("/health/live")

        self.assertEqual(response.status_code, 200)
        self.assertIn("x-request-id", response.headers)
        self.assertEqual(response.json()["service"], "rag-service")
        self.assertEqual(response.json()["check_type"], "liveness")

    def test_index_and_search_wallet_memories(self) -> None:
        index_response = self.client.post(
            "/memories/index",
            json={
                "memories": [
                    {
                        "memory_id": "mem-wallet-01",
                        "user_id": "user-1",
                        "image_key": "captures/wallet-01.jpg",
                        "captured_at": "2026-04-01T08:15:00Z",
                        "caption": "a wallet is on the desk next to the keyboard",
                        "detected_objects": ["wallet", "desk", "keyboard"],
                        "tags": ["office"],
                        "location": {"name": WORKROOM},
                    },
                    {
                        "memory_id": "mem-key-01",
                        "user_id": "user-1",
                        "image_key": "captures/key-01.jpg",
                        "captured_at": "2026-04-01T07:10:00Z",
                        "caption": "keys are inside the drawer",
                        "detected_objects": ["keys", "drawer"],
                        "tags": ["storage"],
                        "location": {"name": ENTRYWAY},
                    },
                ]
            },
        )

        self.assertEqual(index_response.status_code, 200)
        self.assertEqual(index_response.json()["indexed_count"], 2)
        self.assertEqual(index_response.json()["total_user_memories"]["user-1"], 2)

        search_response = self.client.post(
            "/search",
            json={
                "user_id": "user-1",
                "query": WALLET_QUERY,
                "top_k": 3,
            },
        )

        self.assertEqual(search_response.status_code, 200)
        payload = search_response.json()
        self.assertEqual(payload["total_hits"], 1)
        self.assertEqual(payload["hits"][0]["memory_id"], "mem-wallet-01")
        self.assertEqual(payload["hits"][0]["location"]["name"], WORKROOM)
        self.assertEqual(payload["hits"][0]["position_hint"], "\uD0A4\uBCF4\uB4DC \uC606")
        self.assertIn("wallet", " ".join(payload["hits"][0]["matched_terms"]))

    def test_chat_returns_answer_and_supporting_hits(self) -> None:
        self.client.post(
            "/memories/index",
            json={
                "memories": [
                    {
                        "memory_id": "mem-wallet-02",
                        "user_id": "user-99",
                        "image_key": "captures/wallet-02.jpg",
                        "captured_at": "2026-04-01T10:30:00Z",
                        "caption": "a wallet is on top of the shelf",
                        "detected_objects": ["wallet", "shelf"],
                        "location": {"name": LIVING_ROOM},
                    }
                ]
            },
        )

        response = self.client.post(
            "/chat",
            json={
                "user_id": "user-99",
                "query": "\uC9C0\uAC11 \uC5B4\uB514 \uC788\uC5C8\uC5B4?",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["answer_mode"], "template")
        self.assertEqual(payload["total_hits"], 1)
        self.assertEqual(payload["hits"][0]["memory_id"], "mem-wallet-02")
        self.assertIn("mem-wallet-02", payload["answer"])
        self.assertIn(LIVING_ROOM, payload["answer"])
        self.assertEqual(payload["cited_memory_ids"], ["mem-wallet-02"])
        self.assertEqual(payload["confidence"], 0.5)
        self.assertIn("검색 결과를 기반", payload["reason"])

    def test_unknown_item_returns_no_hits(self) -> None:
        self.client.post(
            "/memories/index",
            json={
                "memories": [
                    {
                        "memory_id": "mem-wallet-03",
                        "user_id": "user-2",
                        "image_key": "captures/wallet-03.jpg",
                        "captured_at": "2026-04-01T08:15:00Z",
                        "caption": "a wallet is on the desk next to the keyboard",
                        "detected_objects": ["wallet", "desk", "keyboard"],
                        "location": {"name": WORKROOM},
                    },
                    {
                        "memory_id": "mem-key-03",
                        "user_id": "user-2",
                        "image_key": "captures/key-03.jpg",
                        "captured_at": "2026-04-01T07:10:00Z",
                        "caption": "keys are inside the drawer",
                        "detected_objects": ["keys", "drawer"],
                        "location": {"name": ENTRYWAY},
                    },
                ]
            },
        )

        response = self.client.post(
            "/search",
            json={
                "user_id": "user-2",
                "query": UMBRELLA_QUERY,
                "top_k": 3,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total_hits"], 0)
        self.assertEqual(payload["hits"], [])

    def test_blank_identifiers_are_rejected(self) -> None:
        response = self.client.post(
            "/memories/index",
            json={
                "memories": [
                    {
                        "memory_id": "   ",
                        "user_id": "user-3",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_empty_searchable_text_does_not_crash(self) -> None:
        index_response = self.client.post(
            "/memories/index",
            json={
                "memories": [
                    {
                        "memory_id": "mem-empty-01",
                        "user_id": "user-empty",
                    }
                ]
            },
        )

        self.assertEqual(index_response.status_code, 200)

        search_response = self.client.post(
            "/search",
            json={
                "user_id": "user-empty",
                "query": WALLET_QUERY,
                "top_k": 3,
            },
        )

        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.json()["total_hits"], 0)
        self.assertEqual(search_response.json()["hits"], [])

        chat_response = self.client.post(
            "/chat",
            json={
                "user_id": "user-empty",
                "query": WALLET_QUERY,
                "top_k": 3,
            },
        )

        self.assertEqual(chat_response.status_code, 200)
        self.assertEqual(chat_response.json()["total_hits"], 0)
        self.assertEqual(chat_response.json()["hits"], [])
        self.assertEqual(chat_response.json()["answer_mode"], "template")
        self.assertEqual(chat_response.json().get("cited_memory_ids"), [])


if __name__ == "__main__":
    unittest.main()
