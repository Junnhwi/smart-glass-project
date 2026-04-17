from __future__ import annotations

import unittest

from src.api.intake import build_capture_upload_response, build_worker_task_kwargs
from src.api.pipeline import (
    CapturePipelineError,
    CapturePipelineSettings,
    CaptureProcessingPipeline,
    CaptureTaskOutcome,
)
from src.api.schemas import CaptureUploadRequest


class RecordingTaskTransport:
    def __init__(self, outcome: CaptureTaskOutcome) -> None:
        self.outcome = outcome
        self.last_kwargs: dict[str, object] | None = None
        self.last_timeout_sec: float | None = None

    def submit_and_wait(
        self,
        *,
        task_kwargs: dict[str, object],
        timeout_sec: float,
    ) -> CaptureTaskOutcome:
        self.last_kwargs = task_kwargs
        self.last_timeout_sec = timeout_sec
        return self.outcome


class RecordingRagIndexClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.last_worker_result: dict[str, object] | None = None

    def index_vlm_result(self, worker_result: dict[str, object]) -> dict[str, object]:
        self.last_worker_result = worker_result
        return self.response


class FailingRagIndexClient:
    def __init__(self, message: str) -> None:
        self.message = message
        self.last_worker_result: dict[str, object] | None = None

    def index_vlm_result(self, worker_result: dict[str, object]) -> dict[str, object]:
        self.last_worker_result = worker_result
        raise CapturePipelineError(self.message)


class CaptureProcessingPipelineTests(unittest.TestCase):
    def _build_payload(self) -> CaptureUploadRequest:
        return CaptureUploadRequest(
            captureId="capture-10",
            requestId="req-10",
            memoryId="mem-10",
            userId="user-10",
            taskType="metadata",
            capturedAt="2026-04-07T08:00:00Z",
            fileName="glass-photo.jpg",
            imageUrl="https://example.com/captures/glass-photo.jpg",
        )

    def _build_worker_result(self, payload: CaptureUploadRequest) -> tuple[dict[str, object], dict[str, object]]:
        capture_response = build_capture_upload_response(payload)
        expected_kwargs = build_worker_task_kwargs(capture_response)
        worker_result: dict[str, object] = {
            "status": "success",
            "requestId": capture_response.requestId,
            "taskType": capture_response.taskType,
            "memoryId": capture_response.memoryId,
            "userId": capture_response.userId,
            "capturedAt": capture_response.capturedAt,
            "sourceImage": {
                "imageKey": capture_response.sourceImage.imageKey,
                "imageUrl": capture_response.sourceImage.imageUrl,
                "contentType": capture_response.sourceImage.contentType,
            },
            "metadata": {
                "caption": "a laptop is on the table",
                "sceneSummary": "tabletop scene",
                "detectedObjects": ["laptop"],
                "tags": ["desk"],
                "ocrText": "notes",
                "positionHint": "on the table",
                "location": {"name": "office"},
            },
            "pipelineOutput": {
                "scene_summary": "tabletop scene",
                "location_context": "office desk",
                "objects": [],
            },
        }
        return worker_result, expected_kwargs

    def test_pipeline_dispatches_worker_and_skips_rag_when_disabled(self) -> None:
        payload = self._build_payload()
        worker_result, expected_kwargs = self._build_worker_result(payload)
        task_transport = RecordingTaskTransport(
            CaptureTaskOutcome(task_id="task-123", result=worker_result)
        )
        pipeline = CaptureProcessingPipeline(
            settings=CapturePipelineSettings(
                broker_url="redis://redis:6379/0",
                result_backend_url="redis://redis:6379/1",
                enable_rag_index=False,
                worker_timeout_sec=15.0,
            ),
            task_transport=task_transport,
            rag_index_client=None,
        )

        response = pipeline.process(payload)

        self.assertEqual(task_transport.last_kwargs, expected_kwargs)
        self.assertEqual(task_transport.last_timeout_sec, 15.0)
        self.assertEqual(response.status, "completed")
        self.assertEqual(response.capture.captureId, "capture-10")
        self.assertEqual(response.worker.taskId, "task-123")
        self.assertEqual(response.worker.status, "success")
        self.assertEqual(response.ragIndex.status, "skipped")
        self.assertEqual(response.ragIndex.endpoint, "/memories/index/vlm")

    def test_pipeline_dispatches_worker_and_indexes_rag_when_enabled(self) -> None:
        payload = self._build_payload()
        worker_result, expected_kwargs = self._build_worker_result(payload)
        task_transport = RecordingTaskTransport(
            CaptureTaskOutcome(task_id="task-123", result=worker_result)
        )
        rag_client = RecordingRagIndexClient(
            {"indexed_count": 1, "total_user_memories": {"user-10": 1}}
        )
        pipeline = CaptureProcessingPipeline(
            settings=CapturePipelineSettings(
                broker_url="redis://redis:6379/0",
                result_backend_url="redis://redis:6379/1",
                enable_rag_index=True,
                rag_service_base_url="http://rag-service:8000",
                worker_timeout_sec=15.0,
                rag_timeout_sec=10.0,
            ),
            task_transport=task_transport,
            rag_index_client=rag_client,
        )

        response = pipeline.process(payload)

        self.assertEqual(task_transport.last_kwargs, expected_kwargs)
        self.assertEqual(task_transport.last_timeout_sec, 15.0)
        self.assertEqual(rag_client.last_worker_result, worker_result)
        self.assertEqual(response.status, "completed")
        self.assertEqual(response.capture.captureId, "capture-10")
        self.assertEqual(response.worker.taskId, "task-123")
        self.assertEqual(response.worker.status, "success")
        self.assertEqual(response.ragIndex.endpoint, "/memories/index/vlm")
        self.assertEqual(response.ragIndex.indexedCount, 1)
        self.assertEqual(response.ragIndex.totalUserMemories["user-10"], 1)

    def test_pipeline_returns_partial_when_optional_rag_index_fails(self) -> None:
        payload = self._build_payload()
        worker_result, _ = self._build_worker_result(payload)
        task_transport = RecordingTaskTransport(
            CaptureTaskOutcome(task_id="task-123", result=worker_result)
        )
        rag_client = FailingRagIndexClient("rag-service indexing failed: timeout")
        pipeline = CaptureProcessingPipeline(
            settings=CapturePipelineSettings(
                broker_url="redis://redis:6379/0",
                result_backend_url="redis://redis:6379/1",
                enable_rag_index=True,
                rag_service_base_url="http://rag-service:8000",
                worker_timeout_sec=15.0,
                rag_timeout_sec=10.0,
            ),
            task_transport=task_transport,
            rag_index_client=rag_client,
        )

        response = pipeline.process(payload)

        self.assertEqual(response.status, "partial")
        self.assertEqual(response.worker.status, "success")
        self.assertEqual(response.ragIndex.status, "error")
        self.assertEqual(response.ragIndex.error, "rag-service indexing failed: timeout")

    def test_pipeline_requires_rag_service_url_when_rag_is_enabled(self) -> None:
        with self.assertRaisesRegex(
            CapturePipelineError,
            "RAG indexing is enabled but RAG_SERVICE_URL is not configured",
        ):
            CaptureProcessingPipeline.from_settings(
                CapturePipelineSettings(
                    broker_url="redis://redis:6379/0",
                    result_backend_url="redis://redis:6379/1",
                    enable_rag_index=True,
                )
            )


if __name__ == "__main__":
    unittest.main()
