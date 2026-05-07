from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

from src.api.auth import (
    INTERNAL_SERVICE_TOKEN_HEADER,
    INTERNAL_SERVICE_TOKEN_ENV,
    build_bearer_authorization_header,
    build_internal_service_token,
)
from src.api.main import app
from src.database.memory_store import MemoryStoreOutcome
from src.modules.media.service import GalleryItem
from src.modules.search.service import GeneratedAnswer, SearchHit


class FakeCapturePipeline:
    def check_health(self) -> None:
        pass


class FakeMemoryQueryService:
    def __init__(self) -> None:
        self.last_search_args: tuple[str, str, int] | None = None
        self.last_chat_args: tuple[str, str, int] | None = None

    def search(self, user_id: str, query: str, top_k: int) -> list[SearchHit]:
        self.last_search_args = (user_id, query, top_k)
        return []

    def chat(
        self,
        user_id: str,
        query: str,
        top_k: int,
    ) -> tuple[GeneratedAnswer, list[SearchHit]]:
        self.last_chat_args = (user_id, query, top_k)
        return (
            GeneratedAnswer(
                text="no result",
                mode="template",
                cited_memory_ids=[],
                confidence=0.1,
                reason="test",
            ),
            [],
        )

    def check_health(self) -> None:
        pass


class FakeMediaAccessService:
    def __init__(self) -> None:
        self.last_gallery_args: tuple[str, int] | None = None
        self.gallery_item = GalleryItem(
            memory_id="mem-wallet-01",
            image_key="captures/user-1/mem-wallet-01.jpg",
            image_url="https://example.com/captures/mem-wallet-01.jpg",
            captured_at="2026-04-07T08:00:00Z",
            caption="wallet on the desk",
            scene_summary="desk scene",
            position_hint="on the desk",
        )

    def list_gallery_items(self, *, user_id: str, limit: int) -> list[GalleryItem]:
        self.last_gallery_args = (user_id, limit)
        return [self.gallery_item]

    def check_health(self) -> None:
        pass


class FakeMemoryStoreClient:
    def __init__(self) -> None:
        self.last_worker_result: dict[str, object] | None = None

    def persist_vlm_result(self, worker_result: dict[str, object]) -> MemoryStoreOutcome:
        self.last_worker_result = worker_result
        return MemoryStoreOutcome(
            stored_count=1,
            total_user_memories={str(worker_result["userId"]): 1},
        )

    def check_health(self) -> None:
        pass


def build_valid_inference_payload() -> dict[str, object]:
    return {
        "status": "success",
        "requestId": "req-auth-001",
        "taskType": "metadata",
        "memoryId": "mem-auth-001",
        "userId": "user-1",
        "capturedAt": "2026-04-30T09:00:00Z",
        "sourceImage": {
            "imageKey": "captures/user-1/2026/04/30/cap-auth.jpg",
            "contentType": "image/jpeg",
        },
        "metadata": {
            "caption": "wallet on the desk",
            "sceneSummary": "desk scene",
            "detectedObjects": ["wallet"],
            "tags": ["wallet"],
            "positionHint": "on the desk",
            "location": {"name": "workspace"},
        },
        "pipelineOutput": {
            "scene_summary": "desk scene",
            "location_context": "workspace",
            "objects": [],
        },
    }


class ApiServerAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_internal_service_token = os.environ.get(
            INTERNAL_SERVICE_TOKEN_ENV
        )
        self.original_memory_store_client_factory = (
            app.state.memory_store_client_factory
        )
        os.environ[INTERNAL_SERVICE_TOKEN_ENV] = "test-internal-service-token"
        app.state.capture_pipeline = FakeCapturePipeline()
        app.state.memory_query_service = FakeMemoryQueryService()
        app.state.media_access_service = FakeMediaAccessService()
        app.state.memory_store_client = FakeMemoryStoreClient()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.state.capture_pipeline = None
        app.state.memory_query_service = None
        app.state.media_access_service = None
        app.state.memory_store_client = None
        app.state.memory_store_client_factory = (
            self.original_memory_store_client_factory
        )
        if self.original_internal_service_token is None:
            os.environ.pop(INTERNAL_SERVICE_TOKEN_ENV, None)
        else:
            os.environ[INTERNAL_SERVICE_TOKEN_ENV] = (
                self.original_internal_service_token
            )

    def test_search_requires_authorization_header(self) -> None:
        response = self.client.post(
            "/search",
            json={
                "user_id": "user-1",
                "query": "wallet",
                "top_k": 3,
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("Authorization", response.json()["detail"])

    def test_search_rejects_authenticated_user_mismatch(self) -> None:
        response = self.client.post(
            "/search",
            headers={
                "Authorization": build_bearer_authorization_header("user-2"),
            },
            json={
                "user_id": "user-1",
                "query": "wallet",
                "top_k": 3,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("does not match", response.json()["detail"])
        self.assertIsNone(app.state.memory_query_service.last_search_args)

    def test_media_gallery_rejects_authenticated_user_mismatch(self) -> None:
        response = self.client.post(
            "/media/gallery",
            headers={
                "Authorization": build_bearer_authorization_header("user-2"),
            },
            json={
                "userId": "user-1",
                "limit": 20,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertIsNone(app.state.media_access_service.last_gallery_args)

    def test_inference_results_require_internal_service_token(self) -> None:
        response = self.client.post(
            "/memories/inference-results",
            json=build_valid_inference_payload(),
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("internal service token", response.json()["detail"])
        self.assertIsNone(app.state.memory_store_client.last_worker_result)

    def test_inference_results_accept_internal_service_token(self) -> None:
        response = self.client.post(
            "/memories/inference-results",
            headers={
                INTERNAL_SERVICE_TOKEN_HEADER: build_internal_service_token(),
            },
            json=build_valid_inference_payload(),
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["memoryId"], "mem-auth-001")
        self.assertIsNotNone(app.state.memory_store_client.last_worker_result)

    def test_inference_results_return_503_when_internal_service_token_is_missing(
        self,
    ) -> None:
        os.environ.pop(INTERNAL_SERVICE_TOKEN_ENV, None)

        response = self.client.post(
            "/memories/inference-results",
            headers={
                INTERNAL_SERVICE_TOKEN_HEADER: "test-internal-service-token",
            },
            json=build_valid_inference_payload(),
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn(INTERNAL_SERVICE_TOKEN_ENV, response.json()["detail"])
        self.assertIsNone(app.state.memory_store_client.last_worker_result)

    def test_inference_results_return_503_when_memory_store_init_fails(
        self,
    ) -> None:
        app.state.memory_store_client = None

        def build_failing_memory_store_client() -> FakeMemoryStoreClient:
            raise ValueError(
                "API_CAPTURE_DATABASE_URL is required for memory storage"
            )

        app.state.memory_store_client_factory = build_failing_memory_store_client

        response = self.client.post(
            "/memories/inference-results",
            headers={
                INTERNAL_SERVICE_TOKEN_HEADER: build_internal_service_token(),
            },
            json=build_valid_inference_payload(),
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("API_CAPTURE_DATABASE_URL", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
