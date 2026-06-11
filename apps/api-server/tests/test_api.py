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
from src.api.intake import build_capture_upload_response
from src.api.main import app
from src.api.schemas import (
    CaptureMemoryStoreExecutionPayload,
    CaptureProcessingResponse,
    CaptureUploadRequest,
    CaptureWorkerExecutionPayload,
)
from src.api.pipeline import CaptureTaskStatus
from src.database.memory_store import MemoryLocation, MemoryRecord, MemoryStoreOutcome
from src.modules.media.service import (
    GalleryItem,
    MediaAccessUrl,
    MediaUrlSignerConfigError,
)
from src.modules.users.service import DeviceAuthorization
from src.modules.search.service import GeneratedAnswer, SearchHit


class FakeCapturePipeline:
    def __init__(self) -> None:
        self.last_payload: CaptureUploadRequest | None = None
        self.last_task_id: str | None = None
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

    def submit(self, payload: CaptureUploadRequest):
        self.last_payload = payload
        capture = build_capture_upload_response(payload)
        return "task-123", capture

    def get_task_status(self, task_id: str) -> CaptureTaskStatus:
        self.last_task_id = task_id
        capture = build_capture_upload_response(
            CaptureUploadRequest(
                captureId="capture-001",
                requestId="req-001",
                memoryId="mem-001",
                userId="user-1",
                deviceId="glass-001",
                taskType="metadata",
                capturedAt="2026-04-07T08:00:00Z",
                fileName="smart-glass-photo.jpg",
            )
        )
        return CaptureTaskStatus(
            task_id=task_id,
            state="SUCCESS",
            result={
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
            },
            error=None,
        )

    def build_memory_store_payload(self, worker_result: dict[str, object]):
        return (
            "completed",
            CaptureMemoryStoreExecutionPayload(
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


class FakeMediaAccessService:
    def __init__(self) -> None:
        self.last_issue_access_url_args: tuple[str, str, int] | None = None
        self.last_issue_access_urls_args: tuple[str, tuple[str, ...], int] | None = None
        self.last_gallery_args: tuple[str, int] | None = None
        self.last_deleted_image_key: str | None = None
        self.should_fail = False
        self.should_configure_fail = False
        self.should_forbid = False
        self.health_checked = False
        self.gallery_item = GalleryItem(
            memory_id="mem-wallet-01",
            image_key="captures/user-1/mem-wallet-01.jpg",
            image_url="https://example.com/captures/mem-wallet-01.jpg",
            captured_at="2026-04-07T08:00:00Z",
            caption="wallet on the desk next to the keyboard",
            scene_summary="desk scene",
            position_hint="keyboard 옆",
        )

    def issue_access_url(
        self,
        *,
        user_id: str,
        image_key: str,
        expires_in_sec: int | None = None,
    ) -> MediaAccessUrl:
        if self.should_configure_fail:
            raise MediaUrlSignerConfigError("Missing required bucket configuration")
        if self.should_fail:
            raise RuntimeError("storage signer unavailable")
        if self.should_forbid:
            raise PermissionError("imageKey does not belong to the requested user")
        resolved_expiration = 300 if expires_in_sec is None else expires_in_sec
        self.last_issue_access_url_args = (user_id, image_key, resolved_expiration)
        return MediaAccessUrl(
            image_key=image_key,
            access_url=f"https://signed.example.com/{image_key}?expires={resolved_expiration}",
            expires_at="2026-04-17T00:05:00Z",
            expires_in_sec=resolved_expiration,
        )

    def issue_access_urls(
        self,
        *,
        user_id: str,
        image_keys: list[str],
        expires_in_sec: int | None = None,
    ) -> list[MediaAccessUrl]:
        if self.should_configure_fail:
            raise MediaUrlSignerConfigError("Missing required bucket configuration")
        if self.should_fail:
            raise RuntimeError("storage signer unavailable")
        if self.should_forbid:
            raise PermissionError("imageKey does not belong to the requested user")
        resolved_expiration = 300 if expires_in_sec is None else expires_in_sec
        self.last_issue_access_urls_args = (
            user_id,
            tuple(image_keys),
            resolved_expiration,
        )
        return [
            MediaAccessUrl(
                image_key=image_key,
                access_url=f"https://signed.example.com/{image_key}?expires={resolved_expiration}",
                expires_at="2026-04-17T00:05:00Z",
                expires_in_sec=resolved_expiration,
            )
            for image_key in image_keys
        ]

    def list_gallery_items(self, *, user_id: str, limit: int) -> list[GalleryItem]:
        self.last_gallery_args = (user_id, limit)
        return [self.gallery_item]

    def delete_media_object(self, *, image_key: str) -> str:
        if self.should_configure_fail:
            raise MediaUrlSignerConfigError("Missing required bucket configuration")
        if self.should_fail:
            raise RuntimeError("storage delete unavailable")
        self.last_deleted_image_key = image_key
        return image_key

    def check_health(self) -> None:
        self.health_checked = True


class FakeMemoryStoreClient:
    backend_name = "postgres"

    def __init__(self) -> None:
        self.last_worker_result: dict[str, object] | None = None
        self.last_get_args: tuple[str, str] | None = None
        self.last_delete_args: tuple[str, str] | None = None
        self.should_fail = False
        self.record = MemoryRecord(
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
        )

    def persist_vlm_result(self, worker_result: dict[str, object]) -> MemoryStoreOutcome:
        if self.should_fail:
            raise RuntimeError("memory database unavailable")
        self.last_worker_result = worker_result
        return MemoryStoreOutcome(
            stored_count=1,
            total_user_memories={str(worker_result["userId"]): 3},
        )

    def get_by_memory_id(self, user_id: str, memory_id: str) -> MemoryRecord | None:
        if self.should_fail:
            raise RuntimeError("memory database unavailable")
        self.last_get_args = (user_id, memory_id)
        if self.record.user_id == user_id and self.record.memory_id == memory_id:
            return self.record
        return None

    def delete_by_memory_id(self, user_id: str, memory_id: str) -> MemoryRecord | None:
        if self.should_fail:
            raise RuntimeError("memory database unavailable")
        self.last_delete_args = (user_id, memory_id)
        if self.record.user_id == user_id and self.record.memory_id == memory_id:
            return self.record
        return None

    def check_health(self) -> None:
        pass


class FakeUserDeviceService:
    def __init__(self) -> None:
        self.last_authorized_device_id: str | None = None
        self.authorization_status = "allowed"
        self.authorization_user_id = "user-1"
        self.should_fail = False
        self.should_health_fail = False
        self.health_checked = False

    def authorize_device(self, *, device_id: str) -> DeviceAuthorization:
        if self.should_fail:
            raise RuntimeError("user registry unavailable")
        self.last_authorized_device_id = device_id
        if self.authorization_status == "blocked":
            return DeviceAuthorization(
                status="blocked",
                device_id=device_id,
                user_id=None,
            )
        return DeviceAuthorization(
            status="allowed",
            device_id=device_id,
            user_id=self.authorization_user_id,
        )

    def check_health(self) -> None:
        self.health_checked = True
        if self.should_health_fail:
            raise RuntimeError("user registry unavailable")


class FakeAuthService:
    def __init__(self) -> None:
        self.health_checked = False
        self.should_health_fail = False

    def check_health(self) -> None:
        self.health_checked = True
        if self.should_health_fail:
            raise RuntimeError("auth storage unavailable")


class ApiServerCaptureIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_internal_service_token = os.environ.get(
            INTERNAL_SERVICE_TOKEN_ENV
        )
        os.environ[INTERNAL_SERVICE_TOKEN_ENV] = "test-internal-service-token"
        self.fake_pipeline = FakeCapturePipeline()
        self.fake_memory_query_service = FakeMemoryQueryService()
        self.fake_media_access_service = FakeMediaAccessService()
        self.fake_memory_store_client = FakeMemoryStoreClient()
        self.fake_user_device_service = FakeUserDeviceService()
        self.fake_auth_service = FakeAuthService()
        app.state.capture_pipeline = self.fake_pipeline
        app.state.memory_query_service = self.fake_memory_query_service
        app.state.media_access_service = self.fake_media_access_service
        app.state.memory_store_client = self.fake_memory_store_client
        app.state.user_device_service = self.fake_user_device_service
        app.state.auth_service = self.fake_auth_service
        self.client = TestClient(
            app,
            headers={
                "Authorization": build_bearer_authorization_header("user-1"),
            },
        )

    def tearDown(self) -> None:
        app.state.capture_pipeline = None
        app.state.memory_query_service = None
        app.state.media_access_service = None
        app.state.memory_store_client = None
        app.state.user_device_service = None
        app.state.auth_service = None
        if self.original_internal_service_token is None:
            os.environ.pop(INTERNAL_SERVICE_TOKEN_ENV, None)
        else:
            os.environ[INTERNAL_SERVICE_TOKEN_ENV] = (
                self.original_internal_service_token
            )

    def test_capture_processing_endpoint_enqueues_pipeline(self) -> None:
        payload = {
            "captureId": "capture-001",
            "requestId": "req-001",
            "memoryId": "mem-001",
            "userId": "user-1",
            "deviceId": "glass-001",
            "taskType": "metadata",
            "capturedAt": "2026-04-07T08:00:00Z",
            "fileName": "smart-glass-photo.jpg",
            "sourceImage": {
                "imageUrl": "https://example.com/captures/smart-glass-photo.jpg",
            },
        }

        response = self.client.post("/media/captures", json=payload)

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(body["status"], "accepted")
        self.assertEqual(body["taskId"], "task-123")
        self.assertEqual(body["capture"]["captureId"], "capture-001")
        self.assertEqual(body["capture"]["dispatch"]["status"], "prepared")
        self.assertEqual(body["capture"]["sourceImage"]["imageKey"], "captures/user-1/2026/04/07/capture-001-smart-glass-photo.jpg")
        self.assertEqual(body["worker"]["taskId"], "task-123")
        self.assertEqual(body["worker"]["status"], "queued")
        self.assertIsNotNone(self.fake_pipeline.last_payload)
        self.assertEqual(self.fake_pipeline.last_payload.userId, "user-1")
        self.assertEqual(self.fake_pipeline.last_payload.deviceId, "glass-001")
        self.assertEqual(
            self.fake_user_device_service.last_authorized_device_id,
            "glass-001",
        )

    def test_capture_task_polling_returns_completed_result(self) -> None:
        response = self.client.get("/media/captures/tasks/task-123")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["taskId"], "task-123")
        self.assertEqual(body["worker"]["status"], "success")
        self.assertEqual(body["worker"]["result"]["memoryId"], "mem-001")
        self.assertEqual(body["memoryStore"]["backend"], "disabled")
        self.assertEqual(body["memoryStore"]["status"], "skipped")
        self.assertEqual(self.fake_pipeline.last_task_id, "task-123")

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

    def test_media_access_url_endpoint_returns_presigned_url(self) -> None:
        response = self.client.post(
            "/media/access-url",
            json={
                "userId": "user-1",
                "imageKey": "captures/user-1/mem-wallet-01.jpg",
                "expiresInSec": 180,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["imageKey"], "captures/user-1/mem-wallet-01.jpg")
        self.assertEqual(body["expiresInSec"], 180)
        self.assertIn("https://signed.example.com/", body["accessUrl"])
        self.assertEqual(
            self.fake_media_access_service.last_issue_access_url_args,
            ("user-1", "captures/user-1/mem-wallet-01.jpg", 180),
        )

    def test_media_access_url_endpoint_surfaces_signer_failure(self) -> None:
        self.fake_media_access_service.should_fail = True

        response = self.client.post(
            "/media/access-url",
            json={
                "userId": "user-1",
                "imageKey": "captures/user-1/mem-wallet-01.jpg",
            },
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("storage signer unavailable", response.json()["detail"])

    def test_media_access_endpoints_treat_config_errors_as_server_errors(self) -> None:
        self.fake_media_access_service.should_configure_fail = True

        cases = [
            (
                "/media/access-url",
                {
                    "userId": "user-1",
                    "imageKey": "captures/user-1/mem-wallet-01.jpg",
                },
            ),
            (
                "/media/access-urls",
                {
                    "userId": "user-1",
                    "imageKeys": [
                        "captures/user-1/mem-wallet-01.jpg",
                        "captures/user-1/mem-wallet-02.jpg",
                    ],
                },
            ),
        ]

        for path, payload in cases:
            with self.subTest(path=path):
                response = self.client.post(path, json=payload)
                self.assertEqual(response.status_code, 503)
                self.assertIn("bucket", response.json()["detail"].lower())

    def test_media_access_url_endpoint_rejects_non_owned_image(self) -> None:
        self.fake_media_access_service.should_forbid = True

        response = self.client.post(
            "/media/access-url",
            json={
                "userId": "user-1",
                "imageKey": "captures/user-2/private-photo.jpg",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("does not belong", response.json()["detail"])

    def test_media_gallery_endpoint_returns_metadata_items(self) -> None:
        response = self.client.post(
            "/media/gallery",
            json={
                "userId": "user-1",
                "limit": 20,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalItems"], 1)
        self.assertEqual(body["items"][0]["memoryId"], "mem-wallet-01")
        self.assertEqual(body["items"][0]["imageKey"], "captures/user-1/mem-wallet-01.jpg")
        self.assertEqual(self.fake_media_access_service.last_gallery_args, ("user-1", 20))

    def test_media_access_urls_endpoint_returns_multiple_presigned_urls(self) -> None:
        response = self.client.post(
            "/media/access-urls",
            json={
                "userId": "user-1",
                "imageKeys": [
                    "captures/user-1/mem-wallet-01.jpg",
                    "captures/user-1/mem-wallet-02.jpg",
                ],
                "expiresInSec": 240,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalItems"], 2)
        self.assertEqual(body["items"][0]["imageKey"], "captures/user-1/mem-wallet-01.jpg")
        self.assertEqual(
            self.fake_media_access_service.last_issue_access_urls_args,
            (
                "user-1",
                (
                    "captures/user-1/mem-wallet-01.jpg",
                    "captures/user-1/mem-wallet-02.jpg",
                ),
                240,
            ),
        )

    def test_inference_result_endpoint_stores_success_payload(self) -> None:
        response = self.client.post(
            "/memories/inference-results",
            headers={
                INTERNAL_SERVICE_TOKEN_HEADER: build_internal_service_token(),
            },
            json={
                "status": "success",
                "requestId": "req-earbuds-001",
                "taskType": "metadata",
                "memoryId": "mem-earbuds-001",
                "userId": "user-1",
                "capturedAt": "2026-04-30T09:00:00Z",
                "sourceImage": {
                    "imageKey": "captures/user-1/2026/04/30/cap-earbuds.jpg",
                    "imageUrl": "https://example.com/cap-earbuds.jpg",
                    "contentType": "image/jpeg",
                },
                "metadata": {
                    "caption": "earbuds on the desk next to the laptop",
                    "sceneSummary": "desk scene with earbuds",
                    "detectedObjects": ["earbuds", "desk", "laptop"],
                    "tags": ["earbuds", "workspace"],
                    "ocrText": None,
                    "positionHint": "next to laptop",
                    "location": {"name": "workspace"},
                },
                "pipelineOutput": {
                    "scene_summary": "desk scene with earbuds",
                    "location_context": "workspace",
                    "objects": [
                        {
                            "name": "earbuds",
                            "nearby_objects": ["laptop"],
                            "visual_features": {"brand": None},
                        }
                    ],
                },
                "providerMetadata": {
                    "modelKey": "qwen2.5-vl-7b",
                    "modelId": "Qwen/Qwen2.5-VL-7B-Instruct",
                    "modelFamily": "qwen-vl",
                    "quantization": "4bit",
                    "dtype": "float16",
                    "provider": "huggingface-transformers",
                    "capabilities": {
                        "detectedObjects": True,
                        "tags": True,
                        "positionHint": True,
                        "sceneSummary": True,
                        "ocrText": True,
                        "location": True,
                    },
                },
                "runtime": {"latencySec": 1.25, "peakMemoryMb": 512.0},
            },
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "stored")
        self.assertEqual(body["memoryId"], "mem-earbuds-001")
        self.assertEqual(body["userId"], "user-1")
        self.assertEqual(body["storedCount"], 1)
        self.assertEqual(body["totalUserMemories"], {"user-1": 3})
        self.assertIsNotNone(self.fake_memory_store_client.last_worker_result)
        self.assertEqual(
            self.fake_memory_store_client.last_worker_result["metadata"]["caption"],
            "earbuds on the desk next to the laptop",
        )

    def test_inference_result_endpoint_rejects_error_payloads(self) -> None:
        response = self.client.post(
            "/memories/inference-results",
            headers={
                INTERNAL_SERVICE_TOKEN_HEADER: build_internal_service_token(),
            },
            json={
                "status": "error",
                "requestId": "req-failed-001",
                "taskType": "metadata",
                "memoryId": "mem-failed-001",
                "userId": "user-1",
                "capturedAt": "2026-04-30T09:00:00Z",
                "sourceImage": {
                    "imageKey": "captures/user-1/2026/04/30/cap-failed.jpg",
                },
                "metadata": {"caption": "failed image"},
            },
        )

        self.assertEqual(response.status_code, 422)

    def test_delete_memory_deletes_object_and_memory_record(self) -> None:
        response = self.client.delete(
            "/memories/mem-wallet-01",
            params={"userId": "user-1"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "deleted")
        self.assertEqual(body["memoryId"], "mem-wallet-01")
        self.assertEqual(body["imageKey"], "captures/user-1/mem-wallet-01.jpg")
        self.assertTrue(body["objectDeleted"])
        self.assertEqual(
            self.fake_memory_store_client.last_get_args,
            ("user-1", "mem-wallet-01"),
        )
        self.assertEqual(
            self.fake_media_access_service.last_deleted_image_key,
            "captures/user-1/mem-wallet-01.jpg",
        )
        self.assertEqual(
            self.fake_memory_store_client.last_delete_args,
            ("user-1", "mem-wallet-01"),
        )

    def test_delete_memory_returns_404_for_missing_memory(self) -> None:
        response = self.client.delete(
            "/memories/missing-memory",
            params={"userId": "user-1"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"])

    def test_delete_memory_keeps_db_record_when_storage_delete_fails(self) -> None:
        self.fake_media_access_service.should_fail = True

        response = self.client.delete(
            "/memories/mem-wallet-01",
            params={"userId": "user-1"},
        )

        self.assertEqual(response.status_code, 502)
        self.assertIn("storage delete unavailable", response.json()["detail"])
        self.assertIsNone(self.fake_memory_store_client.last_delete_args)

    def test_chat_endpoint_returns_answer_and_hits(self) -> None:
        response = self.client.post(
            "/chat",
            json={
                "user_id": "user-1",
                "query": "\uc9c0\uac11 \uc5b4\ub514 \uc788\uc5c8\uc5b4?",
                "top_k": 2,
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
            deviceId="glass-002",
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

    def test_capture_registration_normalizes_explicit_image_key(self) -> None:
        payload = {
            "captureId": "capture-003",
            "requestId": "req-003",
            "memoryId": "mem-003",
            "userId": "user-3",
            "deviceId": "glass-003",
            "capturedAt": "2026-04-07T11:00:00Z",
            "sourceImage": {
                "imageKey": " captures//user-3//2026/04/07//photo.jpg ",
            },
        }

        self.fake_user_device_service.authorization_user_id = "user-3"

        response = self.client.post("/media/captures", json=payload)

        self.assertEqual(response.status_code, 202)
        body = response.json()
        self.assertEqual(
            body["capture"]["sourceImage"]["imageKey"],
            "captures/user-3/2026/04/07/photo.jpg",
        )
        self.assertEqual(body["capture"]["sourceImage"]["fileName"], "photo.jpg")
        self.assertEqual(body["taskId"], "task-123")
        self.assertEqual(body["worker"]["status"], "queued")

    def test_capture_registration_rejects_url_as_image_key(self) -> None:
        self.fake_user_device_service.authorization_user_id = "user-4"

        response = self.client.post(
            "/media/captures",
            json={
                "captureId": "capture-004",
                "requestId": "req-004",
                "memoryId": "mem-004",
                "userId": "user-4",
                "deviceId": "glass-004",
                "sourceImage": {
                    "imageKey": "https://storage.example.com/captures/user-4/photo.jpg",
                },
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("relative object key", response.json()["detail"])

    def test_capture_registration_rejects_cross_user_image_key(self) -> None:
        self.fake_user_device_service.authorization_user_id = "user-5"

        response = self.client.post(
            "/media/captures",
            json={
                "captureId": "capture-005",
                "requestId": "req-005",
                "memoryId": "mem-005",
                "userId": "user-5",
                "deviceId": "glass-005",
                "sourceImage": {
                    "imageKey": "captures/user-6/private-photo.jpg",
                },
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("requesting user's captures prefix", response.json()["detail"])

    def test_capture_registration_rejects_non_capture_image_key(self) -> None:
        self.fake_user_device_service.authorization_user_id = "user-6"

        response = self.client.post(
            "/media/captures",
            json={
                "captureId": "capture-006",
                "requestId": "req-006",
                "memoryId": "mem-006",
                "userId": "user-6",
                "deviceId": "glass-006",
                "sourceImage": {
                    "imageKey": "private/user-6/photo.jpg",
                },
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("requesting user's captures prefix", response.json()["detail"])

    def test_capture_registration_requires_device_id(self) -> None:
        response = self.client.post(
            "/media/captures",
            json={
                "captureId": "capture-007",
                "requestId": "req-007",
                "memoryId": "mem-007",
                "userId": "user-1",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("deviceId", str(response.json()["detail"]))

    def test_capture_registration_rejects_blocked_device(self) -> None:
        self.fake_user_device_service.authorization_status = "blocked"

        response = self.client.post(
            "/media/captures",
            json={
                "captureId": "capture-008",
                "requestId": "req-008",
                "memoryId": "mem-008",
                "userId": "user-1",
                "deviceId": "glass-008",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("not allowed", response.json()["detail"])

    def test_capture_registration_rejects_device_user_mismatch(self) -> None:
        self.fake_user_device_service.authorization_user_id = "user-9"

        response = self.client.post(
            "/media/captures",
            json={
                "captureId": "capture-009",
                "requestId": "req-009",
                "memoryId": "mem-009",
                "userId": "user-1",
                "deviceId": "glass-009",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("does not match", response.json()["detail"])

    def test_capture_registration_surfaces_user_device_service_unavailability(self) -> None:
        self.fake_user_device_service.should_fail = True

        response = self.client.post(
            "/media/captures",
            json={
                "captureId": "capture-010",
                "requestId": "req-010",
                "memoryId": "mem-010",
                "userId": "user-1",
                "deviceId": "glass-010",
            },
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("unavailable", response.json()["detail"])

    def test_health_ready(self) -> None:
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "api-server")
        self.assertEqual(response.json()["checks"]["capturePipeline"], "ok")
        self.assertEqual(response.json()["checks"]["memoryQuery"], "ok")
        self.assertEqual(response.json()["checks"]["mediaAccess"], "ok")
        self.assertEqual(response.json()["checks"]["auth"], "ok")
        self.assertEqual(response.json()["checks"]["userDevice"], "ok")
        self.assertTrue(self.fake_pipeline.health_checked)
        self.assertTrue(self.fake_memory_query_service.health_checked)
        self.assertTrue(self.fake_media_access_service.health_checked)
        self.assertTrue(self.fake_auth_service.health_checked)
        self.assertTrue(self.fake_user_device_service.health_checked)

    def test_health_ready_returns_503_when_user_device_service_is_unavailable(self) -> None:
        self.fake_user_device_service.should_health_fail = True

        response = self.client.get("/health/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["userDevice"], "error")
        self.assertIn("unavailable", response.json()["errors"]["userDevice"])


if __name__ == "__main__":
    unittest.main()
