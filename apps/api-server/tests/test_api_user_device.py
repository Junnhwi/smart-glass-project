from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from src.api.main import app
from src.database.user_registry import DeviceRecord, UserRecord
from src.modules.media.service import MediaAccessUrl
from src.modules.users.service import DeviceAuthorization


class FakeUserDeviceService:
    def __init__(self) -> None:
        self.created_users: list[str | None] = []
        self.registered_devices: list[tuple[str, str]] = []
        self.authorized_devices: list[str] = []
        self.should_fail = False
        self.should_lookup_fail = False
        self.should_conflict = False
        self.authorization_status = "allowed"

    def create_user(self, *, user_id: str | None = None) -> UserRecord:
        if self.should_fail:
            raise RuntimeError("user registry unavailable")
        self.created_users.append(user_id)
        return UserRecord(
            user_id=user_id or "user-generated-001",
            created_at="2026-05-05T02:00:00Z",
        )

    def register_device(self, *, user_id: str, device_id: str) -> DeviceRecord:
        if self.should_fail:
            raise RuntimeError("user registry unavailable")
        if self.should_lookup_fail:
            raise LookupError("userId is not registered")
        if self.should_conflict:
            raise ValueError("deviceId is already registered to another user")
        self.registered_devices.append((user_id, device_id))
        return DeviceRecord(
            user_id=user_id,
            device_id=device_id,
            registered_at="2026-05-05T02:05:00Z",
        )

    def authorize_device(self, *, device_id: str) -> DeviceAuthorization:
        if self.should_fail:
            raise RuntimeError("user registry unavailable")
        self.authorized_devices.append(device_id)
        if self.authorization_status == "blocked":
            return DeviceAuthorization(
                status="blocked",
                device_id=device_id,
                user_id=None,
            )
        return DeviceAuthorization(
            status="allowed",
            device_id=device_id,
            user_id="user-1",
        )

    def check_health(self) -> None:
        pass


class FakeMediaAccessService:
    def __init__(self) -> None:
        self.last_issue_upload_url_args: tuple[str, str | None, int | None] | None = None
        self.should_fail = False

    def issue_upload_url(
        self,
        *,
        image_key: str,
        content_type: str | None = None,
        expires_in_sec: int | None = None,
    ) -> MediaAccessUrl:
        if self.should_fail:
            raise RuntimeError("storage signer unavailable")
        self.last_issue_upload_url_args = (image_key, content_type, expires_in_sec)
        resolved_expiration = 300 if expires_in_sec is None else expires_in_sec
        return MediaAccessUrl(
            image_key=image_key,
            access_url=f"https://upload.example.com/{image_key}?expires={resolved_expiration}",
            expires_at="2026-05-05T02:05:00Z",
            expires_in_sec=resolved_expiration,
        )


class ApiServerUserDeviceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_user_device_service_factory = app.state.user_device_service_factory
        self.original_media_access_service_factory = app.state.media_access_service_factory
        self.fake_user_device_service = FakeUserDeviceService()
        self.fake_media_access_service = FakeMediaAccessService()
        app.state.user_device_service = self.fake_user_device_service
        app.state.media_access_service = self.fake_media_access_service
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.state.user_device_service = None
        app.state.media_access_service = None
        app.state.user_device_service_factory = self.original_user_device_service_factory
        app.state.media_access_service_factory = self.original_media_access_service_factory

    def test_create_user_endpoint_accepts_explicit_identifier(self) -> None:
        response = self.client.post(
            "/users",
            json={"userId": "user-1"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "created")
        self.assertEqual(response.json()["userId"], "user-1")
        self.assertEqual(self.fake_user_device_service.created_users, ["user-1"])

    def test_create_user_endpoint_generates_identifier_when_body_missing(self) -> None:
        response = self.client.post("/users")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "created")
        self.assertEqual(response.json()["userId"], "user-generated-001")
        self.assertEqual(self.fake_user_device_service.created_users, [None])

    def test_register_device_endpoint_links_user_and_device(self) -> None:
        response = self.client.post(
            "/devices/register",
            json={"userId": "user-1", "deviceId": "glass-001"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "registered")
        self.assertEqual(response.json()["userId"], "user-1")
        self.assertEqual(response.json()["deviceId"], "glass-001")
        self.assertEqual(
            self.fake_user_device_service.registered_devices,
            [("user-1", "glass-001")],
        )

    def test_register_device_for_user_path_endpoint_links_user_and_device(self) -> None:
        response = self.client.post(
            "/users/user-2/devices",
            json={"deviceId": "glass-002"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "registered")
        self.assertEqual(response.json()["userId"], "user-2")
        self.assertEqual(response.json()["deviceId"], "glass-002")
        self.assertEqual(
            self.fake_user_device_service.registered_devices,
            [("user-2", "glass-002")],
        )

    def test_register_device_returns_404_when_user_is_missing(self) -> None:
        self.fake_user_device_service.should_lookup_fail = True

        response = self.client.post(
            "/devices/register",
            json={"userId": "user-404", "deviceId": "glass-404"},
        )

        self.assertEqual(response.status_code, 404)
        self.assertIn("not registered", response.json()["detail"])

    def test_register_device_returns_409_when_device_belongs_to_other_user(self) -> None:
        self.fake_user_device_service.should_conflict = True

        response = self.client.post(
            "/devices/register",
            json={"userId": "user-2", "deviceId": "glass-001"},
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("already registered", response.json()["detail"])

    def test_upload_authorization_returns_allowed_user(self) -> None:
        response = self.client.post(
            "/media/upload-authorizations",
            json={
                "deviceId": "glass-001",
                "captureId": "capture-001",
                "requestId": "req-001",
                "memoryId": "mem-001",
                "capturedAt": "2026-05-05T11:00:00+09:00",
                "fileName": "photo.png",
                "contentType": "image/png",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "allowed")
        self.assertEqual(body["userId"], "user-1")
        self.assertEqual(body["upload"]["method"], "direct")
        self.assertEqual(body["upload"]["captureId"], "capture-001")
        self.assertEqual(body["upload"]["requestId"], "req-001")
        self.assertEqual(body["upload"]["memoryId"], "mem-001")
        self.assertEqual(body["upload"]["capturedAt"], "2026-05-05T02:00:00Z")
        self.assertEqual(
            body["upload"]["uploadUrl"],
            "https://upload.example.com/captures/user-1/2026/05/05/capture-001-photo.png?expires=300",
        )
        self.assertEqual(body["upload"]["expiresAt"], "2026-05-05T02:05:00Z")
        self.assertEqual(body["upload"]["expiresInSec"], 300)
        self.assertEqual(
            body["upload"]["sourceImage"]["imageKey"],
            "captures/user-1/2026/05/05/capture-001-photo.png",
        )
        self.assertEqual(body["upload"]["sourceImage"]["contentType"], "image/png")
        self.assertEqual(body["upload"]["sourceImage"]["fileName"], "photo.png")
        self.assertEqual(self.fake_user_device_service.authorized_devices, ["glass-001"])
        self.assertEqual(
            self.fake_media_access_service.last_issue_upload_url_args,
            (
                "captures/user-1/2026/05/05/capture-001-photo.png",
                "image/png",
                None,
            ),
        )

    def test_upload_authorization_returns_blocked_response_for_unknown_device(self) -> None:
        self.fake_user_device_service.authorization_status = "blocked"

        response = self.client.post(
            "/media/upload-authorizations",
            json={"deviceId": "glass-999"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["status"], "blocked")
        self.assertIsNone(response.json()["userId"])
        self.assertIsNone(response.json()["upload"])
        self.assertEqual(self.fake_user_device_service.authorized_devices, ["glass-999"])

    def test_upload_authorization_rejects_invalid_explicit_image_key(self) -> None:
        response = self.client.post(
            "/media/upload-authorizations",
            json={
                "deviceId": "glass-001",
                "imageKey": "captures/user-2/private-photo.jpg",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("captures prefix", response.json()["detail"])

    def test_user_device_endpoints_surface_service_unavailability(self) -> None:
        self.fake_user_device_service.should_fail = True

        cases = [
            ("/users", {}),
            ("/devices/register", {"userId": "user-1", "deviceId": "glass-001"}),
            ("/media/upload-authorizations", {"deviceId": "glass-001"}),
        ]

        for path, payload in cases:
            with self.subTest(path=path):
                response = self.client.post(path, json=payload)
                self.assertEqual(response.status_code, 503)
                self.assertIn("unavailable", response.json()["detail"])

    def test_upload_authorization_returns_503_when_upload_signer_fails(self) -> None:
        self.fake_media_access_service.should_fail = True

        response = self.client.post(
            "/media/upload-authorizations",
            json={"deviceId": "glass-001", "fileName": "photo.jpg"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("storage signer unavailable", response.json()["detail"])

    def test_user_device_endpoints_return_503_when_factory_configuration_is_missing(self) -> None:
        app.state.user_device_service = None

        def build_failing_user_device_service() -> FakeUserDeviceService:
            raise ValueError("API_CAPTURE_DATABASE_URL is required for user/device storage")

        app.state.user_device_service_factory = build_failing_user_device_service

        response = self.client.post("/users", json={})

        self.assertEqual(response.status_code, 503)
        self.assertIn("API_CAPTURE_DATABASE_URL", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
