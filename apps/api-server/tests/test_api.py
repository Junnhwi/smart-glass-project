from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from src.api.intake import build_capture_upload_response
from src.api.main import app
from src.api.schemas import (
    CaptureMemoryStoreExecutionPayload,
    CaptureProcessingResponse,
    CaptureUploadRequest,
    CaptureWorkerExecutionPayload,
)
from src.database.memory_store import MemoryLocation, MemoryRecord
from src.modules.search.service import GeneratedAnswer, SearchHit


class FakeCapturePipeline:
    def __init__(self) -> None:
        self.last_payload: CaptureUploadRequest | None = None
        self.health_checked = False

    def process(self, payload: CaptureUploadRequest) -> CaptureProcessingResponse:
        self.last_payload = payload
        capture = build_capture_upload_response(payload)
        worker_result = {
            "status": "success",
            "requestId": capture.requestId,
            "taskType": capture.taskType,
            "memoryId": capture.memoryId,
            "userId": capture.userId,
            "capturedAt": capture.capturedAt,
            "sourceImage": {
                "imageKey": capture.sourceImage.imageKey,
                "imageUrl": capture.sourceImage.imageUrl,
                "contentType": capture.sourceImage.contentType,
            },
            "metadata": {
                "caption": "desk scene",
                "sceneSummary": "desk scene",
                "detectedObjects": ["laptop", "apple pencil"],
                "tags": ["desk"],
                "ocrText": "notes",
                "positionHint": "on the desk",
                "location": {"name": "cafe"},
            },
            "pipelineOutput": {
                "scene_summary": "desk scene",
                "location_context": "cafe desk",
                "objects": [],
            },
        }
        return CaptureProcessingResponse(
            status="completed",
            capture=capture,
            worker=CaptureWorkerExecutionPayload(
                taskId="task-123",
                status="success",
                result=worker_result,
                error=None,
            ),
            memoryStore=CaptureMemoryStoreExecutionPayload(
                backend="disabled",
                status="skipped",
                storedCount=None,
                totalUserMemories={},
                error=None,
            ),
        )

    def check_health(self) -> None:
        self.health_checked = True


class FakeMemoryQueryService:
    def __init__(self) -> None:
        self.last_search_args: tuple[str, str, int] | None = None
        self.last_chat_args: tuple[str, str, int] | None = None
        self.health_checked = False
        self.hit = SearchHit(
            memory=MemoryRecord(
                memory_id="mem-wallet-01",
                user_id="user-1",
                image_key="captures/user-1/mem-wallet-01.jpg",
                image_url="https://example.com/captures/mem-wallet-01.jpg",
                captured_at="2026-04-07T08:00:00Z",
                caption="wallet on the desk next to the keyboard",
                scene_summary="desk scene",
                detected_objects=["wallet", "desk", "keyboard"],
                tags=["office"],
                ocr_text="notes",
                note=None,
                position_hint="keyboard 옆",
                location=MemoryLocation(name="workspace"),
            ),
            score=0.72,
            lexical_score=0.72,
            matched_terms=["wallet", "desk"],
        )

    def search(self, user_id: str, query: str, top_k: int) -> list[SearchHit]:
        self.last_search_args = (user_id, query, top_k)
        return [self.hit]

    def chat(self, user_id: str, query: str, top_k: int) -> tuple[GeneratedAnswer, list[SearchHit]]:
        self.last_chat_args = (user_id, query, top_k)
        return (
            GeneratedAnswer(
                text="mem-wallet-01\uc5d0\uc11c \uc9c0\uac11\uc774 \ucc45\uc0c1 \uc704\uc5d0 \uc788\uc5c8\uc2b5\ub2c8\ub2e4.",
                mode="template",
                cited_memory_ids=["mem-wallet-01"],
                confidence=0.5,
                reason="\ud15c\ud50c\ub9bf \uc751\ub2f5",
            ),
            [self.hit],
        )

    def check_health(self) -> None:
        self.health_checked = True


class ApiServerCaptureIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_pipeline = FakeCapturePipeline()
        self.fake_memory_query_service = FakeMemoryQueryService()
        app.state.capture_pipeline = self.fake_pipeline
        app.state.memory_query_service = self.fake_memory_query_service
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.state.capture_pipeline = None
        app.state.memory_query_service = None

    def test_capture_processing_endpoint_runs_pipeline(self) -> None:
        payload = {
            "captureId": "capture-001",
            "requestId": "req-001",
            "memoryId": "mem-001",
            "userId": "user-1",
            "taskType": "metadata",
            "capturedAt": "2026-04-07T08:00:00Z",
            "fileName": "smart-glass-photo.jpg",
            "sourceImage": {
                "imageUrl": "https://example.com/captures/smart-glass-photo.jpg",
            },
        }

        response = self.client.post("/media/captures", json=payload)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["capture"]["captureId"], "capture-001")
        self.assertEqual(body["capture"]["dispatch"]["status"], "prepared")
        self.assertEqual(body["capture"]["sourceImage"]["imageKey"], "captures/user-1/2026/04/07/capture-001-smart-glass-photo.jpg")
        self.assertEqual(body["worker"]["taskId"], "task-123")
        self.assertEqual(body["worker"]["status"], "success")
        self.assertEqual(body["memoryStore"]["backend"], "disabled")
        self.assertEqual(body["memoryStore"]["status"], "skipped")
        self.assertIsNotNone(self.fake_pipeline.last_payload)
        self.assertEqual(self.fake_pipeline.last_payload.userId, "user-1")

    def test_search_endpoint_returns_memory_hits(self) -> None:
        response = self.client.post(
            "/search",
            json={
                "user_id": "user-1",
                "query": "\ub0b4 \uc9c0\uac11 \uc5b4\ub514\uc5d0 \uc788\uc5c8\uc9c0?",
                "top_k": 3,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalHits"], 1)
        self.assertEqual(body["hits"][0]["memoryId"], "mem-wallet-01")
        self.assertEqual(body["hits"][0]["imageKey"], "captures/user-1/mem-wallet-01.jpg")
        self.assertEqual(body["hits"][0]["location"]["name"], "workspace")
        self.assertEqual(self.fake_memory_query_service.last_search_args, ("user-1", "\ub0b4 \uc9c0\uac11 \uc5b4\ub514\uc5d0 \uc788\uc5c8\uc9c0?", 3))

    def test_chat_endpoint_returns_answer_and_hits(self) -> None:
        response = self.client.post(
            "/chat",
            json={
                "userId": "user-1",
                "query": "\uc9c0\uac11 \uc5b4\ub514 \uc788\uc5c8\uc5b4?",
                "topK": 2,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["answerMode"], "template")
        self.assertEqual(body["totalHits"], 1)
        self.assertEqual(body["hits"][0]["memoryId"], "mem-wallet-01")
        self.assertEqual(body["citedMemoryIds"], ["mem-wallet-01"])
        self.assertEqual(self.fake_memory_query_service.last_chat_args, ("user-1", "\uc9c0\uac11 \uc5b4\ub514 \uc788\uc5c8\uc5b4?", 2))

    def test_capture_registration_response_can_be_built_directly(self) -> None:
        payload = CaptureUploadRequest(
            captureId="capture-002",
            requestId="req-002",
            memoryId="mem-002",
            userId="user-2",
            capturedAt="2026-04-07T09:30:00Z",
            fileName="cafe-table.png",
            imageUrl="https://example.com/captures/cafe-table.png",
        )

        response = build_capture_upload_response(payload)

        self.assertEqual(response.captureId, "capture-002")
        self.assertEqual(response.inferenceRequest.requestId, "req-002")
        self.assertEqual(response.inferenceRequest.memoryId, "mem-002")
        self.assertEqual(response.inferenceRequest.userId, "user-2")
        self.assertEqual(response.inferenceRequest.sourceImage.imageKey, "captures/user-2/2026/04/07/capture-002-cafe-table.png")
        self.assertEqual(response.sourceImage.fileName, "cafe-table.png")

    def test_health_ready(self) -> None:
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "api-server")
        self.assertEqual(response.json()["checks"]["capturePipeline"], "ok")
        self.assertEqual(response.json()["checks"]["memoryQuery"], "ok")
        self.assertTrue(self.fake_pipeline.health_checked)
        self.assertTrue(self.fake_memory_query_service.health_checked)


if __name__ == "__main__":
    unittest.main()
