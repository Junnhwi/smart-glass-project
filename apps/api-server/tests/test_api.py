from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from src.api.intake import build_capture_upload_response
from src.api.main import app
from src.api.schemas import (
    CaptureProcessingResponse,
    CaptureRagIndexExecutionPayload,
    CaptureUploadRequest,
    CaptureWorkerExecutionPayload,
)


class FakeCapturePipeline:
    def __init__(self) -> None:
        self.last_payload: CaptureUploadRequest | None = None

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
            ragIndex=CaptureRagIndexExecutionPayload(
                endpoint="/memories/index/vlm",
                status="skipped",
                indexedCount=None,
                totalUserMemories={},
                response=None,
                error=None,
            ),
        )


class ApiServerCaptureIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fake_pipeline = FakeCapturePipeline()
        app.state.capture_pipeline = self.fake_pipeline
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.state.capture_pipeline = None

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
        self.assertEqual(body["ragIndex"]["endpoint"], "/memories/index/vlm")
        self.assertEqual(body["ragIndex"]["status"], "skipped")
        self.assertIsNotNone(self.fake_pipeline.last_payload)
        self.assertEqual(self.fake_pipeline.last_payload.userId, "user-1")

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


if __name__ == "__main__":
    unittest.main()
