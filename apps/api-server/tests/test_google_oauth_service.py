from __future__ import annotations

import unittest
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from src.database.auth_store import (
    AuthIdentityRecord,
    AuthOauthHandoffRecord,
    AuthOauthStateRecord,
    AuthUserRecord,
)
from src.modules.auth.oauth import GoogleOauthService


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


class FakeOauthRepository:
    def __init__(self) -> None:
        self.users_by_email: dict[str, AuthUserRecord] = {}
        self.identities: dict[tuple[str, str], AuthIdentityRecord] = {}
        self.oauth_states: dict[str, AuthOauthStateRecord] = {}
        self.oauth_handoffs: dict[str, AuthOauthHandoffRecord] = {}

    def get_auth_identity(
        self,
        *,
        provider: str,
        provider_user_id: str,
    ) -> AuthIdentityRecord | None:
        return self.identities.get((provider, provider_user_id))

    def upsert_auth_identity(
        self,
        *,
        provider: str,
        provider_user_id: str,
        user_id: str,
        email: str | None,
        email_verified: bool,
        display_name: str | None,
        profile_json: str | None,
    ) -> AuthIdentityRecord:
        record = AuthIdentityRecord(
            provider=provider,
            provider_user_id=provider_user_id,
            user_id=user_id,
            email=email,
            email_verified=email_verified,
            display_name=display_name,
            created_at="2026-05-05T00:00:00Z",
            updated_at="2026-05-05T00:00:00Z",
        )
        self.identities[(provider, provider_user_id)] = record
        return record

    def create_oauth_state(
        self,
        *,
        state: str,
        provider: str,
        redirect_uri: str,
        code_verifier: str,
        expires_at: str,
    ) -> AuthOauthStateRecord:
        record = AuthOauthStateRecord(
            state=state,
            provider=provider,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
            expires_at=expires_at,
            consumed_at=None,
            created_at="2026-05-05T00:00:00Z",
        )
        self.oauth_states[state] = record
        return record

    def consume_oauth_state(self, state: str) -> AuthOauthStateRecord | None:
        record = self.oauth_states.get(state)
        if record is None or record.consumed_at is not None:
            return None
        consumed = AuthOauthStateRecord(
            state=record.state,
            provider=record.provider,
            redirect_uri=record.redirect_uri,
            code_verifier=record.code_verifier,
            expires_at=record.expires_at,
            consumed_at="2026-05-05T00:02:00Z",
            created_at=record.created_at,
        )
        self.oauth_states[state] = consumed
        return consumed

    def create_oauth_handoff(
        self,
        *,
        handoff_code: str,
        provider: str,
        user_id: str,
        expires_at: str,
    ) -> AuthOauthHandoffRecord:
        record = AuthOauthHandoffRecord(
            handoff_code=handoff_code,
            provider=provider,
            user_id=user_id,
            expires_at=expires_at,
            consumed_at=None,
            created_at="2026-05-05T00:03:00Z",
        )
        self.oauth_handoffs[handoff_code] = record
        return record

    def consume_oauth_handoff(
        self,
        *,
        handoff_code: str,
        provider: str,
    ) -> AuthOauthHandoffRecord | None:
        record = self.oauth_handoffs.get(handoff_code)
        if record is None or record.provider != provider or record.consumed_at is not None:
            return None
        consumed = AuthOauthHandoffRecord(
            handoff_code=record.handoff_code,
            provider=record.provider,
            user_id=record.user_id,
            expires_at=record.expires_at,
            consumed_at="2026-05-05T00:04:00Z",
            created_at=record.created_at,
        )
        self.oauth_handoffs[handoff_code] = consumed
        return consumed

    def get_auth_user_by_email(self, email: str) -> AuthUserRecord | None:
        return self.users_by_email.get(email)

    def create_auth_user(
        self,
        *,
        user_id: str,
        email: str,
        password_hash: str,
        display_name: str | None,
        role: str,
        status: str,
    ) -> AuthUserRecord:
        if email in self.users_by_email:
            raise ValueError("email is already registered")
        record = AuthUserRecord(
            user_id=user_id,
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            role=role,
            status=status,
            created_at="2026-05-05T00:00:00Z",
            last_login_at=None,
        )
        self.users_by_email[email] = record
        return record


class FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class FakeHttpClient:
    def post(self, url: str, *args, **kwargs) -> FakeHttpResponse:
        return FakeHttpResponse({"access_token": "google-access-token"})

    def get(self, url: str, *args, **kwargs) -> FakeHttpResponse:
        return FakeHttpResponse(
            {
                "sub": "google-user-001",
                "email": "user@example.com",
                "email_verified": True,
                "name": "Google User",
            }
        )


class FakeAuthService:
    def __init__(self) -> None:
        self.last_issue_args: tuple[str, str | None, str | None, str | None] | None = None

    def issue_tokens_for_user(
        self,
        *,
        user_id: str,
        device_id: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> FakeAuthTokenBundle:
        self.last_issue_args = (user_id, device_id, user_agent, ip_address)
        return FakeAuthTokenBundle(
            access_token="jwt-google-token",
            refresh_token="refresh-google-token",
            token_type="Bearer",
            expires_in_sec=900,
            refresh_expires_in_sec=3600,
            user=FakeAuthProfile(
                user_id=user_id,
                email="user@example.com",
                display_name="Google User",
                role="user",
                status="active",
                created_at="2026-05-05T00:00:00Z",
                last_login_at="2026-05-05T00:05:00Z",
            ),
        )


class GoogleOauthServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeOauthRepository()
        self.auth_service = FakeAuthService()
        self.service = GoogleOauthService(
            self.repository,
            self.auth_service,
            client_id="google-client-id",
            client_secret="google-client-secret",
            callback_url="http://localhost:8002/auth/oauth/google/callback",
            http_client=FakeHttpClient(),
            allowed_redirect_uris=(
                "smart-glass-client://oauth",
                "http://localhost:8081/",
            ),
            state_ttl_sec=600,
            handoff_ttl_sec=300,
            password_iterations=100_000,
        )

    def test_start_builds_google_authorization_url(self) -> None:
        start = self.service.start(
            redirect_uri="smart-glass-client://oauth?device_id=glass-001"
        )

        parsed = urlparse(start.authorization_url)
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(query["client_id"][0], "google-client-id")
        self.assertEqual(query["redirect_uri"][0], "http://localhost:8002/auth/oauth/google/callback")
        self.assertEqual(query["state"][0], start.state)
        self.assertEqual(query["code_challenge_method"][0], "S256")

    def test_start_rejects_redirect_uri_outside_allowlist(self) -> None:
        with self.assertRaisesRegex(ValueError, "redirectUri is not allowed"):
            self.service.start(
                redirect_uri="https://attacker.example/oauth"
            )

    def test_handle_callback_creates_identity_and_redirects_back_to_client(self) -> None:
        start = self.service.start(
            redirect_uri="smart-glass-client://oauth?device_id=glass-001"
        )

        redirect_url = self.service.handle_callback(
            authorization_code="google-auth-code",
            state=start.state,
        )

        parsed = urlparse(redirect_url)
        query = parse_qs(parsed.query)
        handoff_code = query["oauth_code"][0]

        self.assertEqual(parsed.scheme, "smart-glass-client")
        self.assertEqual(query["provider"][0], "google")
        self.assertEqual(query["device_id"][0], "glass-001")
        self.assertTrue(handoff_code.startswith("oauth-"))
        self.assertIn(("google", "google-user-001"), self.repository.identities)
        self.assertIn("user@example.com", self.repository.users_by_email)

    def test_handle_callback_error_redirects_with_error_payload(self) -> None:
        start = self.service.start(
            redirect_uri="smart-glass-client://oauth?device_id=glass-001"
        )

        redirect_url = self.service.handle_callback_error(
            state=start.state,
            error="access_denied",
            description="User denied access",
        )

        parsed = urlparse(redirect_url)
        query = parse_qs(parsed.query)

        self.assertEqual(query["oauth_error"][0], "access_denied")
        self.assertEqual(query["oauth_error_description"][0], "User denied access")
        self.assertEqual(query["device_id"][0], "glass-001")

    def test_exchange_handoff_issues_tokens_for_resolved_user(self) -> None:
        start = self.service.start(
            redirect_uri="smart-glass-client://oauth?device_id=glass-001"
        )
        redirect_url = self.service.handle_callback(
            authorization_code="google-auth-code",
            state=start.state,
        )
        handoff_code = parse_qs(urlparse(redirect_url).query)["oauth_code"][0]

        bundle = self.service.exchange_handoff(
            handoff_code=handoff_code,
            device_id="glass-001",
            user_agent="Expo",
            ip_address="127.0.0.1",
        )

        self.assertEqual(bundle.access_token, "jwt-google-token")
        self.assertEqual(bundle.refresh_token, "refresh-google-token")
        self.assertIsNotNone(self.auth_service.last_issue_args)
        self.assertEqual(self.auth_service.last_issue_args[1], "glass-001")
        self.assertEqual(self.auth_service.last_issue_args[2], "Expo")
        self.assertEqual(self.auth_service.last_issue_args[3], "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
