from __future__ import annotations

import unittest
from dataclasses import dataclass
from urllib.parse import quote

from fastapi.testclient import TestClient

from src.api.main import app
from src.database.memory_store import MemoryLocation, MemoryRecord
from src.database.user_registry import DeviceRecord
from src.modules.auth.security import RateLimitExceededError
from src.modules.auth.service import AuthenticatedPrincipal
from src.modules.search.service import GeneratedAnswer, SearchHit


@dataclass(frozen=True, slots=True)
class FakeAuthProfile:
    user_id: str
    email: str
    display_name: str
    role: str
    status: str
    created_at: str
    last_login_at: str | None


@dataclass(frozen=True, slots=True)
class FakeAuthTokenBundle:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in_sec: int
    refresh_expires_in_sec: int
    user: FakeAuthProfile


@dataclass(frozen=True, slots=True)
class FakeLogoutResult:
    revoked_access_token: bool
    revoked_refresh_token: bool


@dataclass(frozen=True, slots=True)
class FakeOauthStart:
    provider: str
    authorization_url: str
    state: str
    expires_at: str


class FakeAuthService:
    def __init__(self) -> None:
        self.should_reject_login = False
        self.sign_up_error: Exception | None = None
        self.last_signup_payload: dict[str, str | None] | None = None
        self.last_login_payload: dict[str, str | None] | None = None
        self.last_refresh_token: str | None = None
        self.last_logout_input: tuple[str | None, str | None] | None = None
        self.last_list_users_limit: int | None = None
        self.last_update_user_payload: dict[str, str | None] | None = None
        self.profile = FakeAuthProfile(
            user_id="user-auth-001",
            email="user@example.com",
            display_name="Auth User",
            role="user",
            status="active",
            created_at="2026-05-05T00:00:00Z",
            last_login_at="2026-05-05T00:10:00Z",
        )
        self.admin_profile = FakeAuthProfile(
            user_id="admin-1",
            email="admin@example.com",
            display_name="Admin User",
            role="admin",
            status="active",
            created_at="2026-05-05T00:00:00Z",
            last_login_at="2026-05-05T00:20:00Z",
        )

    def sign_up(
        self,
        *,
        email: str,
        password: str,
        display_name: str | None = None,
        user_id: str | None = None,
        role: str = "user",
        device_id: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> FakeAuthTokenBundle:
        if self.sign_up_error is not None:
            raise self.sign_up_error
        self.last_signup_payload = {
            "email": email,
            "display_name": display_name,
            "user_id": user_id,
            "device_id": device_id,
            "user_agent": user_agent,
            "ip_address": ip_address,
        }
        return FakeAuthTokenBundle(
            access_token="jwt-signup-token",
            refresh_token="refresh-signup-token",
            token_type="Bearer",
            expires_in_sec=900,
            refresh_expires_in_sec=3600,
            user=self.profile,
        )

    def login(
        self,
        *,
        email: str,
        password: str,
        device_id: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> FakeAuthTokenBundle:
        if self.should_reject_login:
            raise PermissionError("Invalid email or password")
        self.last_login_payload = {
            "email": email,
            "device_id": device_id,
            "user_agent": user_agent,
            "ip_address": ip_address,
        }
        return FakeAuthTokenBundle(
            access_token="jwt-login-token",
            refresh_token="refresh-login-token",
            token_type="Bearer",
            expires_in_sec=900,
            refresh_expires_in_sec=3600,
            user=self.profile,
        )

    def refresh(
        self,
        *,
        refresh_token: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> FakeAuthTokenBundle:
        self.last_refresh_token = refresh_token
        return FakeAuthTokenBundle(
            access_token="jwt-refresh-token",
            refresh_token="refresh-rotated-token",
            token_type="Bearer",
            expires_in_sec=900,
            refresh_expires_in_sec=3600,
            user=self.profile,
        )

    def logout(
        self,
        *,
        refresh_token: str | None = None,
        access_token: str | None = None,
    ) -> FakeLogoutResult:
        self.last_logout_input = (refresh_token, access_token)
        return FakeLogoutResult(
            revoked_access_token=bool(access_token),
            revoked_refresh_token=bool(refresh_token),
        )

    def authenticate_access_token(self, token: str) -> AuthenticatedPrincipal:
        if token == "jwt-user-1":
            return AuthenticatedPrincipal(
                user_id="user-1",
                role="user",
                token_type="access",
                session_id="ses-001",
                token_jti="atk-001",
            )
        if token == "jwt-admin-1":
            return AuthenticatedPrincipal(
                user_id="admin-1",
                role="admin",
                token_type="access",
                session_id="ses-admin-001",
                token_jti="atk-admin-001",
            )
        raise PermissionError("Access token is invalid")

    def get_user_profile(self, user_id: str) -> FakeAuthProfile:
        if user_id == self.admin_profile.user_id:
            return self.admin_profile
        if user_id != self.profile.user_id and user_id != "user-1":
            raise LookupError("auth user is not registered")
        if user_id == "user-1":
            return FakeAuthProfile(
                user_id="user-1",
                email="user1@example.com",
                display_name="User One",
                role="user",
                status="active",
                created_at="2026-05-05T00:00:00Z",
                last_login_at="2026-05-05T00:10:00Z",
            )
        return self.profile

    def list_users(self, *, limit: int = 100) -> list[FakeAuthProfile]:
        self.last_list_users_limit = limit
        return [
            self.admin_profile,
            self.profile,
        ][:limit]

    def update_user(
        self,
        *,
        user_id: str,
        display_name: str | None = None,
        role: str | None = None,
        status: str | None = None,
    ):
        self.last_update_user_payload = {
            "user_id": user_id,
            "display_name": display_name,
            "role": role,
            "status": status,
        }
        updated_profile = FakeAuthProfile(
            user_id=self.profile.user_id if user_id == self.profile.user_id else user_id,
            email=self.profile.email if user_id == self.profile.user_id else f"{user_id}@example.com",
            display_name=display_name or self.profile.display_name,
            role=role or self.profile.role,
            status=status or self.profile.status,
            created_at=self.profile.created_at,
            last_login_at=self.profile.last_login_at,
        )

        class FakeAuthUserUpdateResult:
            def __init__(self, user: FakeAuthProfile, revoked_session_count: int) -> None:
                self.user = user
                self.revoked_session_count = revoked_session_count

        return FakeAuthUserUpdateResult(
            updated_profile,
            1 if status == "disabled" else 0,
        )

    def check_health(self) -> None:
        pass


class FakeGoogleOauthService:
    def __init__(self, token_bundle: FakeAuthTokenBundle) -> None:
        self.token_bundle = token_bundle
        self.disallowed_redirect_uris: set[str] = set()
        self.last_start_redirect_uri: str | None = None
        self.last_callback_args: tuple[str, str] | None = None
        self.last_callback_error_args: tuple[str, str, str | None] | None = None
        self.last_exchange_args: tuple[str, str | None, str | None, str | None] | None = None

    def start(self, *, redirect_uri: str) -> FakeOauthStart:
        if redirect_uri in self.disallowed_redirect_uris:
            raise ValueError("redirectUri is not allowed")
        self.last_start_redirect_uri = redirect_uri
        return FakeOauthStart(
            provider="google",
            authorization_url="https://accounts.google.com/o/oauth2/v2/auth?state=oauth-state-001",
            state="oauth-state-001",
            expires_at="2026-05-05T00:10:00Z",
        )

    def handle_callback(
        self,
        *,
        authorization_code: str,
        state: str,
    ) -> str:
        self.last_callback_args = (authorization_code, state)
        return (
            "smart-glass-client://oauth"
            "?oauth_code=oauth-handoff-001"
            "&provider=google"
            "&device_id=glass-001"
        )

    def handle_callback_error(
        self,
        *,
        state: str,
        error: str,
        description: str | None = None,
    ) -> str:
        self.last_callback_error_args = (state, error, description)
        return (
            "smart-glass-client://oauth"
            f"?oauth_error={quote(error)}"
            f"&oauth_error_description={quote(description or '')}"
        )

    def exchange_handoff(
        self,
        *,
        handoff_code: str,
        device_id: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> FakeAuthTokenBundle:
        self.last_exchange_args = (
            handoff_code,
            device_id,
            user_agent,
            ip_address,
        )
        return self.token_bundle


class FakeUserDeviceService:
    def __init__(self) -> None:
        self.registered_devices: list[tuple[str, str]] = []

    def register_device(self, *, user_id: str, device_id: str) -> DeviceRecord:
        self.registered_devices.append((user_id, device_id))
        return DeviceRecord(
            user_id=user_id,
            device_id=device_id,
            registered_at="2026-05-05T00:11:00Z",
        )

    def check_health(self) -> None:
        pass


class FakeMemoryQueryService:
    def __init__(self) -> None:
        self.last_search_args: tuple[str, str, int] | None = None
        self.last_chat_args: tuple[str, str, int] | None = None
        self.last_recent_args: tuple[str, int] | None = None

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

    def recent_memories(self, user_id: str, limit: int) -> list[MemoryRecord]:
        self.last_recent_args = (user_id, limit)
        return [
            MemoryRecord(
                memory_id="mem-recent-001",
                user_id=user_id,
                image_key="captures/user-1/recent-001.jpg",
                image_url=None,
                captured_at="2026-05-05T00:30:00Z",
                caption="wallet on the desk",
                scene_summary="workspace desk scene",
                detected_objects=["wallet", "desk"],
                tags=["workspace"],
                ocr_text=None,
                note=None,
                position_hint="on the desk",
                location=MemoryLocation(name="workspace"),
            )
        ]

    def check_health(self) -> None:
        pass


class FakeAuthSecurityService:
    def __init__(self) -> None:
        self.rate_limited_policy_keys: set[str] = set()
        self.enforced_limits: list[tuple[str, str | None]] = []
        self.recorded_events: list[dict[str, object | None]] = []

    def enforce_rate_limit(self, *, policy_key: str, identifier: str | None) -> None:
        self.enforced_limits.append((policy_key, identifier))
        if policy_key in self.rate_limited_policy_keys:
            raise RateLimitExceededError(
                policy_key=policy_key,
                identifier=identifier or "anonymous",
                retry_after_sec=60,
            )

    def record_event(
        self,
        *,
        event_type: str,
        outcome: str,
        user_id: str | None = None,
        email: str | None = None,
        provider: str | None = None,
        device_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.recorded_events.append(
            {
                "event_type": event_type,
                "outcome": outcome,
                "user_id": user_id,
                "email": email,
                "provider": provider,
                "device_id": device_id,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "metadata": metadata,
            }
        )


class ApiServerRealAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_auth_service_factory = app.state.auth_service_factory
        self.original_auth_security_service_factory = app.state.auth_security_service_factory
        self.original_google_oauth_service_factory = app.state.google_oauth_service_factory
        self.original_user_device_service_factory = app.state.user_device_service_factory
        self.fake_auth_service = FakeAuthService()
        self.fake_auth_security_service = FakeAuthSecurityService()
        self.fake_google_oauth_service = FakeGoogleOauthService(
            self.fake_auth_service.login(
                email="user@example.com",
                password="password123",
            )
        )
        self.fake_user_device_service = FakeUserDeviceService()
        self.fake_memory_query_service = FakeMemoryQueryService()
        app.state.auth_service = self.fake_auth_service
        app.state.auth_security_service = self.fake_auth_security_service
        app.state.google_oauth_service = self.fake_google_oauth_service
        app.state.user_device_service = self.fake_user_device_service
        app.state.memory_query_service = self.fake_memory_query_service
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.state.auth_service = None
        app.state.auth_security_service = None
        app.state.google_oauth_service = None
        app.state.user_device_service = None
        app.state.memory_query_service = None
        app.state.auth_service_factory = self.original_auth_service_factory
        app.state.auth_security_service_factory = self.original_auth_security_service_factory
        app.state.google_oauth_service_factory = self.original_google_oauth_service_factory
        app.state.user_device_service_factory = self.original_user_device_service_factory

    def test_signup_endpoint_returns_token_bundle(self) -> None:
        response = self.client.post(
            "/auth/signup",
            json={
                "email": "user@example.com",
                "password": "password123",
                "displayName": "Auth User",
                "deviceId": "glass-001",
            },
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "authenticated")
        self.assertEqual(body["accessToken"], "jwt-signup-token")
        self.assertEqual(body["user"]["email"], "user@example.com")
        self.assertEqual(self.fake_auth_service.last_signup_payload["device_id"], "glass-001")
        self.assertEqual(
            self.fake_auth_security_service.enforced_limits[:2],
            [
                ("auth.signup.ip", "testclient"),
                ("auth.signup.email", "user@example.com"),
            ],
        )
        self.assertEqual(
            self.fake_auth_security_service.recorded_events[-1]["outcome"],
            "succeeded",
        )

    def test_signup_endpoint_returns_409_for_duplicate_email(self) -> None:
        self.fake_auth_service.sign_up_error = ValueError("email is already registered")

        response = self.client.post(
            "/auth/signup",
            json={
                "email": "user@example.com",
                "password": "password123",
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("already registered", response.json()["detail"])

    def test_login_endpoint_surfaces_invalid_credentials(self) -> None:
        self.fake_auth_service.should_reject_login = True

        response = self.client.post(
            "/auth/login",
            json={
                "email": "user@example.com",
                "password": "wrong-password",
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertIn("Invalid email or password", response.json()["detail"])
        self.assertEqual(
            self.fake_auth_security_service.recorded_events[-1]["outcome"],
            "failed",
        )

    def test_login_endpoint_returns_429_when_rate_limited(self) -> None:
        self.fake_auth_security_service.rate_limited_policy_keys.add("auth.login.ip")

        response = self.client.post(
            "/auth/login",
            json={
                "email": "user@example.com",
                "password": "password123",
            },
        )

        self.assertEqual(response.status_code, 429)
        self.assertIn("Too many requests", response.json()["detail"])
        self.assertEqual(
            self.fake_auth_security_service.recorded_events[-1]["outcome"],
            "rate_limited",
        )

    def test_refresh_endpoint_rotates_refresh_token(self) -> None:
        response = self.client.post(
            "/auth/refresh",
            json={"refreshToken": "refresh-token-001"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["refreshToken"], "refresh-rotated-token")
        self.assertEqual(self.fake_auth_service.last_refresh_token, "refresh-token-001")

    def test_logout_endpoint_forwards_refresh_and_access_tokens(self) -> None:
        response = self.client.post(
            "/auth/logout",
            headers={"Authorization": "Bearer jwt-user-1"},
            json={"refreshToken": "refresh-token-001"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["revokedRefreshToken"])
        self.assertTrue(response.json()["revokedAccessToken"])
        self.assertEqual(
            self.fake_auth_service.last_logout_input,
            ("refresh-token-001", "jwt-user-1"),
        )

    def test_auth_me_endpoint_accepts_jwt_access_token(self) -> None:
        response = self.client.get(
            "/auth/me",
            headers={"Authorization": "Bearer jwt-user-1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["userId"], "user-1")
        self.assertEqual(response.json()["email"], "user1@example.com")

    def test_admin_auth_users_endpoint_requires_admin_role(self) -> None:
        response = self.client.get(
            "/admin/auth/users",
            headers={"Authorization": "Bearer jwt-user-1"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("required role", response.json()["detail"])

    def test_admin_auth_users_endpoint_lists_users_for_admin(self) -> None:
        response = self.client.get(
            "/admin/auth/users",
            headers={"Authorization": "Bearer jwt-admin-1"},
            params={"limit": 10},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["totalUsers"], 2)
        self.assertEqual(self.fake_auth_service.last_list_users_limit, 10)
        self.assertEqual(body["items"][0]["role"], "admin")

    def test_admin_auth_user_update_endpoint_changes_role_and_status(self) -> None:
        response = self.client.patch(
            "/admin/auth/users/user-auth-001",
            headers={"Authorization": "Bearer jwt-admin-1"},
            json={
                "displayName": "Renamed User",
                "role": "admin",
                "status": "disabled",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "updated")
        self.assertEqual(body["user"]["displayName"], "Renamed User")
        self.assertEqual(body["user"]["role"], "admin")
        self.assertEqual(body["user"]["status"], "disabled")
        self.assertEqual(body["revokedSessionCount"], 1)
        self.assertEqual(
            self.fake_auth_service.last_update_user_payload,
            {
                "user_id": "user-auth-001",
                "display_name": "Renamed User",
                "role": "admin",
                "status": "disabled",
            },
        )

    def test_search_endpoint_accepts_jwt_access_token(self) -> None:
        response = self.client.post(
            "/search",
            headers={"Authorization": "Bearer jwt-user-1"},
            json={
                "userId": "user-1",
                "query": "wallet",
                "topK": 3,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.fake_memory_query_service.last_search_args, ("user-1", "wallet", 3))

    def test_recent_memories_endpoint_accepts_jwt_access_token(self) -> None:
        response = self.client.get(
            "/memories/recent",
            headers={"Authorization": "Bearer jwt-user-1"},
            params={
                "userId": "user-1",
                "limit": 10,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["userId"], "user-1")
        self.assertEqual(body["totalItems"], 1)
        self.assertEqual(body["items"][0]["memoryId"], "mem-recent-001")
        self.assertEqual(self.fake_memory_query_service.last_recent_args, ("user-1", 10))

    def test_google_oauth_start_endpoint_returns_authorization_url(self) -> None:
        response = self.client.post(
            "/auth/oauth/google/start",
            json={"redirectUri": "smart-glass-client://oauth?device_id=glass-001"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["provider"], "google")
        self.assertEqual(body["state"], "oauth-state-001")
        self.assertIn("accounts.google.com", body["authorizationUrl"])
        self.assertEqual(
            self.fake_google_oauth_service.last_start_redirect_uri,
            "smart-glass-client://oauth?device_id=glass-001",
        )
        self.assertEqual(
            self.fake_auth_security_service.recorded_events[-1]["event_type"],
            "auth.oauth.google.start",
        )

    def test_google_oauth_start_endpoint_rejects_untrusted_redirect_uri(self) -> None:
        untrusted_redirect_uri = "https://attacker.example/oauth"
        self.fake_google_oauth_service.disallowed_redirect_uris.add(untrusted_redirect_uri)

        response = self.client.post(
            "/auth/oauth/google/start",
            json={"redirectUri": untrusted_redirect_uri},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("redirectUri is not allowed", response.json()["detail"])

    def test_google_oauth_callback_redirects_back_to_client(self) -> None:
        response = self.client.get(
            "/auth/oauth/google/callback",
            params={"code": "google-code-001", "state": "oauth-state-001"},
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("oauth_code=oauth-handoff-001", response.headers["location"])
        self.assertEqual(
            self.fake_google_oauth_service.last_callback_args,
            ("google-code-001", "oauth-state-001"),
        )

    def test_google_oauth_callback_error_redirects_back_to_client(self) -> None:
        response = self.client.get(
            "/auth/oauth/google/callback",
            params={
                "state": "oauth-state-001",
                "error": "access_denied",
                "error_description": "User denied access",
            },
            follow_redirects=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("oauth_error=access_denied", response.headers["location"])
        self.assertEqual(
            self.fake_google_oauth_service.last_callback_error_args,
            ("oauth-state-001", "access_denied", "User denied access"),
        )

    def test_google_oauth_exchange_endpoint_registers_device(self) -> None:
        response = self.client.post(
            "/auth/oauth/google/exchange",
            json={
                "handoffCode": "oauth-handoff-001",
                "deviceId": "glass-001",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "authenticated")
        self.assertEqual(body["accessToken"], "jwt-login-token")
        self.assertEqual(
            self.fake_google_oauth_service.last_exchange_args,
            ("oauth-handoff-001", "glass-001", "testclient", "testclient"),
        )
        self.assertEqual(
            self.fake_user_device_service.registered_devices,
            [("user-auth-001", "glass-001")],
        )
        self.assertEqual(
            self.fake_auth_security_service.recorded_events[-1]["outcome"],
            "succeeded",
        )


if __name__ == "__main__":
    unittest.main()
