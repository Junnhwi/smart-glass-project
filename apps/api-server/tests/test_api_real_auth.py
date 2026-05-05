from __future__ import annotations

import unittest
from dataclasses import dataclass

from fastapi.testclient import TestClient

from src.api.main import app
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


class FakeAuthService:
    def __init__(self) -> None:
        self.should_reject_login = False
        self.last_signup_payload: dict[str, str | None] | None = None
        self.last_login_payload: dict[str, str | None] | None = None
        self.last_refresh_token: str | None = None
        self.last_logout_input: tuple[str | None, str | None] | None = None
        self.profile = FakeAuthProfile(
            user_id="user-auth-001",
            email="user@example.com",
            display_name="Auth User",
            role="user",
            status="active",
            created_at="2026-05-05T00:00:00Z",
            last_login_at="2026-05-05T00:10:00Z",
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
        if token != "jwt-user-1":
            raise PermissionError("Access token is invalid")
        return AuthenticatedPrincipal(
            user_id="user-1",
            role="user",
            token_type="access",
            session_id="ses-001",
            token_jti="atk-001",
        )

    def get_user_profile(self, user_id: str) -> FakeAuthProfile:
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


class ApiServerRealAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_auth_service_factory = app.state.auth_service_factory
        self.fake_auth_service = FakeAuthService()
        self.fake_memory_query_service = FakeMemoryQueryService()
        app.state.auth_service = self.fake_auth_service
        app.state.memory_query_service = self.fake_memory_query_service
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.state.auth_service = None
        app.state.memory_query_service = None
        app.state.auth_service_factory = self.original_auth_service_factory

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


if __name__ == "__main__":
    unittest.main()
