from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from uuid import uuid4

import httpx

from src.database.auth_store import (
    AuthIdentityRecord,
    AuthOauthHandoffRecord,
    AuthOauthStateRecord,
)
from src.modules.auth.service import (
    AuthService,
    AuthTokenBundle,
    _generate_identifier,
    _hash_password,
    _normalize_email,
    _normalize_text,
)


GOOGLE_PROVIDER = "google"
GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc_isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _base64url_encode(value: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _build_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    return _base64url_encode(digest)


def _append_query_params(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    current_query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    current_query.update({key: value for key, value in params.items() if value})
    return urlunparse(
        parsed._replace(query=urlencode(current_query))
    )


def _normalize_redirect_uri(value: str) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        raise ValueError("redirectUri must not be blank")

    parsed = urlparse(normalized)
    if not parsed.scheme:
        raise ValueError("redirectUri must include a URI scheme")
    if parsed.scheme in {"http", "https"} and not parsed.netloc:
        raise ValueError("redirectUri must include a valid host")
    return normalized


@dataclass(frozen=True, slots=True)
class OauthAuthorizationStart:
    provider: str
    authorization_url: str
    state: str
    expires_at: str


@dataclass(frozen=True, slots=True)
class GoogleUserProfile:
    provider: str
    provider_user_id: str
    email: str
    email_verified: bool
    display_name: str
    raw_profile: dict[str, Any]


class OauthRepository(Protocol):
    def get_auth_identity(
        self,
        *,
        provider: str,
        provider_user_id: str,
    ) -> AuthIdentityRecord | None: ...

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
    ) -> AuthIdentityRecord: ...

    def create_oauth_state(
        self,
        *,
        state: str,
        provider: str,
        redirect_uri: str,
        code_verifier: str,
        expires_at: str,
    ) -> AuthOauthStateRecord: ...

    def consume_oauth_state(self, state: str) -> AuthOauthStateRecord | None: ...

    def create_oauth_handoff(
        self,
        *,
        handoff_code: str,
        provider: str,
        user_id: str,
        expires_at: str,
    ) -> AuthOauthHandoffRecord: ...

    def consume_oauth_handoff(
        self,
        *,
        handoff_code: str,
        provider: str,
    ) -> AuthOauthHandoffRecord | None: ...

    def get_auth_user_by_email(self, email: str): ...

    def create_auth_user(
        self,
        *,
        user_id: str,
        email: str,
        password_hash: str,
        display_name: str | None,
        role: str,
        status: str,
    ): ...


class HttpClient(Protocol):
    def post(self, url: str, *args: Any, **kwargs: Any): ...

    def get(self, url: str, *args: Any, **kwargs: Any): ...


class GoogleOauthService:
    def __init__(
        self,
        repository: OauthRepository,
        auth_service: AuthService,
        *,
        client_id: str,
        client_secret: str,
        callback_url: str,
        scopes: str = "openid email profile",
        state_ttl_sec: int = 600,
        handoff_ttl_sec: int = 300,
        password_iterations: int = 600_000,
        http_client: HttpClient | None = None,
    ) -> None:
        self.repository = repository
        self.auth_service = auth_service
        self.client_id = _normalize_text(client_id)
        self.client_secret = _normalize_text(client_secret)
        self.callback_url = _normalize_redirect_uri(callback_url)
        self.scopes = _normalize_text(scopes) or "openid email profile"
        self.state_ttl_sec = max(60, int(state_ttl_sec))
        self.handoff_ttl_sec = max(60, int(handoff_ttl_sec))
        self.password_iterations = max(100_000, int(password_iterations))
        self.http_client = http_client or httpx

        if not self.client_id:
            raise ValueError("API_AUTH_GOOGLE_CLIENT_ID is required")
        if not self.client_secret:
            raise ValueError("API_AUTH_GOOGLE_CLIENT_SECRET is required")

    def start(self, *, redirect_uri: str) -> OauthAuthorizationStart:
        normalized_redirect_uri = _normalize_redirect_uri(redirect_uri)
        state = secrets.token_urlsafe(24)
        code_verifier = secrets.token_urlsafe(64)
        expires_at = _utc_now() + timedelta(seconds=self.state_ttl_sec)
        self.repository.create_oauth_state(
            state=state,
            provider=GOOGLE_PROVIDER,
            redirect_uri=normalized_redirect_uri,
            code_verifier=code_verifier,
            expires_at=_utc_isoformat(expires_at),
        )

        authorization_url = _append_query_params(
            GOOGLE_AUTHORIZATION_URL,
            {
                "client_id": self.client_id,
                "redirect_uri": self.callback_url,
                "response_type": "code",
                "scope": self.scopes,
                "state": state,
                "code_challenge": _build_code_challenge(code_verifier),
                "code_challenge_method": "S256",
                "access_type": "offline",
                "prompt": "consent",
            },
        )
        return OauthAuthorizationStart(
            provider=GOOGLE_PROVIDER,
            authorization_url=authorization_url,
            state=state,
            expires_at=_utc_isoformat(expires_at),
        )

    def _exchange_google_code(
        self,
        *,
        authorization_code: str,
        oauth_state: AuthOauthStateRecord,
    ) -> dict[str, Any]:
        response = self.http_client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": authorization_code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.callback_url,
                "grant_type": "authorization_code",
                "code_verifier": oauth_state.code_verifier,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Google token response is invalid")
        return payload

    def _fetch_google_userinfo(self, access_token: str) -> GoogleUserProfile:
        response = self.http_client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=20.0,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Google userinfo response is invalid")

        provider_user_id = _normalize_text(payload.get("sub"))
        email = _normalize_email(payload.get("email"))
        email_verified = bool(payload.get("email_verified"))
        display_name = _normalize_text(payload.get("name")) or email or provider_user_id

        if not provider_user_id:
            raise RuntimeError("Google userinfo is missing sub")
        if not email:
            raise RuntimeError("Google userinfo is missing email")
        if not email_verified:
            raise PermissionError("Google account email is not verified")

        return GoogleUserProfile(
            provider=GOOGLE_PROVIDER,
            provider_user_id=provider_user_id,
            email=email,
            email_verified=email_verified,
            display_name=display_name,
            raw_profile=payload,
        )

    def _resolve_user_id_for_profile(self, profile: GoogleUserProfile) -> str:
        identity = self.repository.get_auth_identity(
            provider=profile.provider,
            provider_user_id=profile.provider_user_id,
        )
        if identity is not None:
            return identity.user_id

        existing_user = self.repository.get_auth_user_by_email(profile.email)
        if existing_user is not None:
            return existing_user.user_id

        try:
            created_user = self.repository.create_auth_user(
                user_id=_generate_identifier("user"),
                email=profile.email,
                password_hash=_hash_password(
                    secrets.token_urlsafe(48),
                    iterations=self.password_iterations,
                ),
                display_name=profile.display_name,
                role="user",
                status="active",
            )
            return created_user.user_id
        except ValueError as exc:
            if "already registered" not in str(exc):
                raise
            existing_user = self.repository.get_auth_user_by_email(profile.email)
            if existing_user is None:
                raise
            return existing_user.user_id

    def handle_callback_error(
        self,
        *,
        state: str,
        error: str,
        description: str | None = None,
    ) -> str:
        oauth_state = self.repository.consume_oauth_state(state)
        if oauth_state is None:
            raise PermissionError("OAuth state is invalid or already used")
        if oauth_state.provider != GOOGLE_PROVIDER:
            raise PermissionError("OAuth provider is invalid")
        if _utc_now() >= datetime.fromisoformat(oauth_state.expires_at.replace("Z", "+00:00")):
            raise PermissionError("OAuth state has expired")

        return self.build_error_redirect(
            redirect_uri=oauth_state.redirect_uri,
            error=_normalize_text(error) or "oauth_access_denied",
            description=description or "Google sign-in was cancelled or denied.",
        )

    def handle_callback(
        self,
        *,
        authorization_code: str,
        state: str,
    ) -> str:
        oauth_state = self.repository.consume_oauth_state(state)
        if oauth_state is None:
            raise PermissionError("OAuth state is invalid or already used")
        if oauth_state.provider != GOOGLE_PROVIDER:
            raise PermissionError("OAuth provider is invalid")
        if _utc_now() >= datetime.fromisoformat(oauth_state.expires_at.replace("Z", "+00:00")):
            raise PermissionError("OAuth state has expired")

        try:
            token_payload = self._exchange_google_code(
                authorization_code=authorization_code,
                oauth_state=oauth_state,
            )
            google_access_token = _normalize_text(token_payload.get("access_token"))
            if not google_access_token:
                raise RuntimeError("Google token response is missing access_token")

            profile = self._fetch_google_userinfo(google_access_token)
            user_id = self._resolve_user_id_for_profile(profile)
            self.repository.upsert_auth_identity(
                provider=profile.provider,
                provider_user_id=profile.provider_user_id,
                user_id=user_id,
                email=profile.email,
                email_verified=profile.email_verified,
                display_name=profile.display_name,
                profile_json=json.dumps(profile.raw_profile, ensure_ascii=False),
            )

            handoff = self.repository.create_oauth_handoff(
                handoff_code=f"oauth-{uuid4().hex}",
                provider=GOOGLE_PROVIDER,
                user_id=user_id,
                expires_at=_utc_isoformat(
                    _utc_now() + timedelta(seconds=self.handoff_ttl_sec)
                ),
            )
            return _append_query_params(
                oauth_state.redirect_uri,
                {
                    "oauth_code": handoff.handoff_code,
                    "provider": GOOGLE_PROVIDER,
                },
            )
        except PermissionError as exc:
            return self.build_error_redirect(
                redirect_uri=oauth_state.redirect_uri,
                error="oauth_access_denied",
                description=str(exc),
            )
        except Exception:
            return self.build_error_redirect(
                redirect_uri=oauth_state.redirect_uri,
                error="oauth_callback_failed",
                description="Google sign-in could not be completed. Please try again.",
            )

    def build_error_redirect(
        self,
        *,
        redirect_uri: str,
        error: str,
        description: str | None = None,
    ) -> str:
        return _append_query_params(
            redirect_uri,
            {
                "oauth_error": _normalize_text(error) or "oauth_error",
                "oauth_error_description": _normalize_text(description) or "",
                "provider": GOOGLE_PROVIDER,
            },
        )

    def exchange_handoff(
        self,
        *,
        handoff_code: str,
        device_id: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> AuthTokenBundle:
        handoff = self.repository.consume_oauth_handoff(
            handoff_code=handoff_code,
            provider=GOOGLE_PROVIDER,
        )
        if handoff is None:
            raise PermissionError("OAuth handoff code is invalid or already used")
        if _utc_now() >= datetime.fromisoformat(handoff.expires_at.replace("Z", "+00:00")):
            raise PermissionError("OAuth handoff code has expired")

        return self.auth_service.issue_tokens_for_user(
            user_id=handoff.user_id,
            device_id=device_id,
            user_agent=user_agent,
            ip_address=ip_address,
        )


def build_default_google_oauth_service(
    repository: OauthRepository,
    auth_service: AuthService,
) -> GoogleOauthService:
    client_id = os.getenv("API_AUTH_GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("API_AUTH_GOOGLE_CLIENT_SECRET", "").strip()
    callback_url = os.getenv("API_AUTH_GOOGLE_CALLBACK_URL", "").strip()
    scopes = os.getenv("API_AUTH_GOOGLE_SCOPES", "openid email profile").strip()
    state_ttl_sec = int(
        os.getenv("API_AUTH_OAUTH_STATE_TTL_SEC", "600").strip() or "600"
    )
    handoff_ttl_sec = int(
        os.getenv("API_AUTH_OAUTH_HANDOFF_TTL_SEC", "300").strip() or "300"
    )
    password_iterations = int(
        os.getenv("API_AUTH_PASSWORD_ITERATIONS", "600000").strip() or "600000"
    )
    return GoogleOauthService(
        repository=repository,
        auth_service=auth_service,
        client_id=client_id,
        client_secret=client_secret,
        callback_url=callback_url,
        scopes=scopes,
        state_ttl_sec=state_ttl_sec,
        handoff_ttl_sec=handoff_ttl_sec,
        password_iterations=password_iterations,
    )
