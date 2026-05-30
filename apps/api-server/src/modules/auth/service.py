from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import uuid4

from src.database.auth_store import (
    AuthSessionRecord,
    AuthUserRecord,
    build_default_auth_store,
)


ACCESS_TOKEN_TYPE = "access"
JWT_ALGORITHM = "HS256"
JWT_ISSUER = "smart-glass-api"
ALLOWED_AUTH_ROLES = {"user", "admin"}
ALLOWED_AUTH_STATUSES = {"active", "disabled"}


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _normalize_email(value: str | None) -> str:
    return _normalize_text(value).lower()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc_isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * ((4 - len(value) % 4) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _hash_refresh_token(value: str) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        raise ValueError("refreshToken must not be blank")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _hash_password(password: str, *, iterations: int) -> str:
    normalized = str(password or "")
    if len(normalized) < 8:
        raise ValueError("password must be at least 8 characters long")

    salt = secrets.token_bytes(16)
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        normalized.encode("utf-8"),
        salt,
        iterations,
    )
    return (
        f"pbkdf2_sha256${iterations}$"
        f"{_base64url_encode(salt)}$"
        f"{_base64url_encode(derived_key)}"
    )


def _verify_password(password: str, encoded_password_hash: str) -> bool:
    normalized_password_hash = _normalize_text(encoded_password_hash)
    if not normalized_password_hash:
        return False

    try:
        algorithm, iterations_raw, salt_b64, digest_b64 = normalized_password_hash.split(
            "$",
            3,
        )
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    try:
        iterations = int(iterations_raw)
    except ValueError:
        return False

    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        _base64url_decode(salt_b64),
        iterations,
    )
    return hmac.compare_digest(_base64url_encode(derived_key), digest_b64)


def _encode_jwt(payload: dict[str, Any], *, secret: str) -> str:
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    header_segment = _base64url_encode(_json_bytes(header))
    payload_segment = _base64url_encode(_json_bytes(payload))
    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = hmac.new(
        secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    return f"{header_segment}.{payload_segment}.{_base64url_encode(signature)}"


def _decode_jwt(token: str, *, secret: str) -> dict[str, Any]:
    normalized = _normalize_text(token)
    if not normalized:
        raise PermissionError("Access token is missing")

    try:
        header_segment, payload_segment, signature_segment = normalized.split(".")
    except ValueError as exc:
        raise PermissionError("Access token format is invalid") from exc

    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(
        _base64url_encode(expected_signature),
        signature_segment,
    ):
        raise PermissionError("Access token signature is invalid")

    try:
        payload = json.loads(_base64url_decode(payload_segment).decode("utf-8"))
    except Exception as exc:  # pragma: no cover - defensive parse guard
        raise PermissionError("Access token payload is invalid") from exc

    if not isinstance(payload, dict):
        raise PermissionError("Access token payload is invalid")

    if payload.get("iss") != JWT_ISSUER:
        raise PermissionError("Access token issuer is invalid")

    exp = payload.get("exp")
    if not isinstance(exp, int):
        raise PermissionError("Access token expiry is invalid")
    if exp <= int(time.time()):
        raise PermissionError("Access token has expired")

    if payload.get("token_type") != ACCESS_TOKEN_TYPE:
        raise PermissionError("Access token type is invalid")

    return payload


def _ensure_role(value: str | None) -> str:
    normalized = _normalize_text(value) or "user"
    if normalized not in ALLOWED_AUTH_ROLES:
        raise ValueError("role must be one of: user, admin")
    return normalized


def _ensure_status(value: str | None) -> str:
    normalized = _normalize_text(value) or "active"
    if normalized not in ALLOWED_AUTH_STATUSES:
        raise ValueError("status must be one of: active, disabled")
    return normalized


def _generate_identifier(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:12]}"


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    user_id: str
    role: str
    token_type: str
    session_id: str | None = None
    token_jti: str | None = None


@dataclass(frozen=True, slots=True)
class AuthProfile:
    user_id: str
    email: str
    display_name: str
    role: str
    status: str
    created_at: str
    last_login_at: str | None


@dataclass(frozen=True, slots=True)
class AuthTokenBundle:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in_sec: int
    refresh_expires_in_sec: int
    user: AuthProfile


@dataclass(frozen=True, slots=True)
class LogoutResult:
    revoked_access_token: bool
    revoked_refresh_token: bool


@dataclass(frozen=True, slots=True)
class AuthUserUpdateResult:
    user: AuthProfile
    revoked_session_count: int = 0


class AuthRepository(Protocol):
    def create_auth_user(
        self,
        *,
        user_id: str,
        email: str,
        password_hash: str,
        display_name: str | None,
        role: str,
        status: str,
    ) -> AuthUserRecord: ...

    def get_auth_user_by_email(self, email: str) -> AuthUserRecord | None: ...

    def get_auth_user_by_user_id(self, user_id: str) -> AuthUserRecord | None: ...

    def list_auth_users(self, *, limit: int = 100) -> list[AuthUserRecord]: ...

    def update_auth_user(
        self,
        *,
        user_id: str,
        password_hash: str | None = None,
        display_name: str | None = None,
        role: str | None = None,
        status: str | None = None,
    ) -> AuthUserRecord: ...

    def touch_last_login(self, user_id: str) -> AuthUserRecord: ...

    def create_refresh_session(
        self,
        *,
        session_id: str,
        user_id: str,
        refresh_token_hash: str,
        expires_at: str,
        device_id: str | None,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthSessionRecord: ...

    def get_refresh_session_by_token_hash(
        self,
        refresh_token_hash: str,
    ) -> AuthSessionRecord | None: ...

    def revoke_refresh_session(
        self,
        *,
        session_id: str,
        replaced_by_session_id: str | None = None,
    ) -> bool: ...

    def revoke_refresh_sessions_by_user(self, *, user_id: str) -> int: ...

    def revoke_access_token(
        self,
        *,
        jti: str,
        user_id: str,
        expires_at: str,
    ) -> bool: ...

    def is_access_token_revoked(self, jti: str) -> bool: ...

    def check_health(self) -> None: ...


class AuthService:
    def __init__(
        self,
        repository: AuthRepository,
        *,
        jwt_secret: str,
        access_ttl_sec: int = 900,
        refresh_ttl_sec: int = 60 * 60 * 24 * 30,
        password_iterations: int = 600_000,
    ) -> None:
        normalized_secret = _normalize_text(jwt_secret)
        if not normalized_secret:
            raise ValueError("jwt_secret must not be blank")

        self.repository = repository
        self.jwt_secret = normalized_secret
        self.access_ttl_sec = max(60, int(access_ttl_sec))
        self.refresh_ttl_sec = max(300, int(refresh_ttl_sec))
        self.password_iterations = max(100_000, int(password_iterations))

    def _build_profile(self, record: AuthUserRecord) -> AuthProfile:
        return AuthProfile(
            user_id=record.user_id,
            email=record.email,
            display_name=record.display_name or record.user_id,
            role=record.role,
            status=record.status,
            created_at=record.created_at,
            last_login_at=record.last_login_at,
        )

    def _issue_access_token(
        self,
        *,
        user: AuthUserRecord,
        session_id: str,
    ) -> tuple[str, str, str]:
        issued_at = _utc_now()
        expires_at = issued_at + timedelta(seconds=self.access_ttl_sec)
        token_jti = f"atk-{uuid4().hex}"
        token = _encode_jwt(
            {
                "iss": JWT_ISSUER,
                "sub": user.user_id,
                "role": user.role,
                "sid": session_id,
                "jti": token_jti,
                "token_type": ACCESS_TOKEN_TYPE,
                "iat": int(issued_at.timestamp()),
                "exp": int(expires_at.timestamp()),
            },
            secret=self.jwt_secret,
        )
        return token, token_jti, _utc_isoformat(expires_at)

    def _create_session_tokens(
        self,
        *,
        user: AuthUserRecord,
        device_id: str | None,
        user_agent: str | None,
        ip_address: str | None,
    ) -> AuthTokenBundle:
        refresh_token = secrets.token_urlsafe(48)
        refresh_expires_at = _utc_now() + timedelta(seconds=self.refresh_ttl_sec)
        session = self.repository.create_refresh_session(
            session_id=f"ses-{uuid4().hex}",
            user_id=user.user_id,
            refresh_token_hash=_hash_refresh_token(refresh_token),
            expires_at=_utc_isoformat(refresh_expires_at),
            device_id=_normalize_text(device_id) or None,
            user_agent=_normalize_text(user_agent) or None,
            ip_address=_normalize_text(ip_address) or None,
        )
        access_token, _, _ = self._issue_access_token(
            user=user,
            session_id=session.session_id,
        )
        return AuthTokenBundle(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in_sec=self.access_ttl_sec,
            refresh_expires_in_sec=self.refresh_ttl_sec,
            user=self._build_profile(user),
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
    ) -> AuthTokenBundle:
        normalized_email = _normalize_email(email)
        if not normalized_email:
            raise ValueError("email must not be blank")

        normalized_user_id = _normalize_text(user_id) or _generate_identifier("user")
        normalized_display_name = _normalize_text(display_name) or normalized_user_id
        normalized_role = _ensure_role(role)

        created_user = self.repository.create_auth_user(
            user_id=normalized_user_id,
            email=normalized_email,
            password_hash=_hash_password(
                password,
                iterations=self.password_iterations,
            ),
            display_name=normalized_display_name,
            role=normalized_role,
            status="active",
        )
        authenticated_user = self.repository.touch_last_login(created_user.user_id)
        return self._create_session_tokens(
            user=authenticated_user,
            device_id=device_id,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    def login(
        self,
        *,
        email: str,
        password: str,
        device_id: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> AuthTokenBundle:
        normalized_email = _normalize_email(email)
        if not normalized_email:
            raise ValueError("email must not be blank")

        user = self.repository.get_auth_user_by_email(normalized_email)
        if user is None or not _verify_password(password, user.password_hash):
            raise PermissionError("Invalid email or password")

        if _ensure_status(user.status) != "active":
            raise PermissionError("The account is not active")

        authenticated_user = self.repository.touch_last_login(user.user_id)
        return self._create_session_tokens(
            user=authenticated_user,
            device_id=device_id,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    def issue_tokens_for_user(
        self,
        *,
        user_id: str,
        device_id: str | None = None,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> AuthTokenBundle:
        normalized_user_id = _normalize_text(user_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")

        user = self.repository.get_auth_user_by_user_id(normalized_user_id)
        if user is None:
            raise LookupError("auth user is not registered")
        if _ensure_status(user.status) != "active":
            raise PermissionError("The account is not active")

        authenticated_user = self.repository.touch_last_login(user.user_id)
        return self._create_session_tokens(
            user=authenticated_user,
            device_id=device_id,
            user_agent=user_agent,
            ip_address=ip_address,
        )

    def refresh(
        self,
        *,
        refresh_token: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> AuthTokenBundle:
        hashed_refresh_token = _hash_refresh_token(refresh_token)
        session = self.repository.get_refresh_session_by_token_hash(hashed_refresh_token)
        if session is None:
            raise PermissionError("Refresh token is invalid")
        if session.revoked_at:
            raise PermissionError("Refresh token has been revoked")
        if session.expires_at and _utc_now() >= datetime.fromisoformat(
            session.expires_at.replace("Z", "+00:00")
        ):
            raise PermissionError("Refresh token has expired")

        user = self.repository.get_auth_user_by_user_id(session.user_id)
        if user is None:
            raise LookupError("auth user is not registered")
        if _ensure_status(user.status) != "active":
            raise PermissionError("The account is not active")

        refreshed_user = self.repository.touch_last_login(user.user_id)
        next_bundle = self._create_session_tokens(
            user=refreshed_user,
            device_id=session.device_id,
            user_agent=_normalize_text(user_agent) or session.user_agent,
            ip_address=_normalize_text(ip_address) or session.ip_address,
        )
        next_refresh_session = self.repository.get_refresh_session_by_token_hash(
            _hash_refresh_token(next_bundle.refresh_token)
        )
        if next_refresh_session is None:
            raise RuntimeError("Refresh session rotation failed")

        self.repository.revoke_refresh_session(
            session_id=session.session_id,
            replaced_by_session_id=next_refresh_session.session_id,
        )
        return next_bundle

    def logout(
        self,
        *,
        refresh_token: str | None = None,
        access_token: str | None = None,
    ) -> LogoutResult:
        revoked_refresh_token = False
        revoked_access_token = False

        normalized_refresh_token = _normalize_text(refresh_token)
        if normalized_refresh_token:
            session = self.repository.get_refresh_session_by_token_hash(
                _hash_refresh_token(normalized_refresh_token)
            )
            if session is not None:
                revoked_refresh_token = self.repository.revoke_refresh_session(
                    session_id=session.session_id
                )

        normalized_access_token = _normalize_text(access_token)
        if normalized_access_token:
            payload = _decode_jwt(normalized_access_token, secret=self.jwt_secret)
            token_jti = _normalize_text(payload.get("jti"))
            token_subject = _normalize_text(payload.get("sub"))
            token_exp = payload.get("exp")
            if token_jti and token_subject and isinstance(token_exp, int):
                revoked_access_token = self.repository.revoke_access_token(
                    jti=token_jti,
                    user_id=token_subject,
                    expires_at=_utc_isoformat(
                        datetime.fromtimestamp(token_exp, timezone.utc)
                    ),
                )

        return LogoutResult(
            revoked_access_token=revoked_access_token,
            revoked_refresh_token=revoked_refresh_token,
        )

    def authenticate_access_token(self, token: str) -> AuthenticatedPrincipal:
        payload = _decode_jwt(token, secret=self.jwt_secret)
        token_jti = _normalize_text(payload.get("jti"))
        if token_jti and self.repository.is_access_token_revoked(token_jti):
            raise PermissionError("Access token has been revoked")

        user_id = _normalize_text(payload.get("sub"))
        session_id = _normalize_text(payload.get("sid")) or None
        if not user_id:
            raise PermissionError("Access token subject is missing")

        user = self.repository.get_auth_user_by_user_id(user_id)
        if user is None:
            raise PermissionError("Authenticated user does not exist")
        if _ensure_status(user.status) != "active":
            raise PermissionError("The account is not active")
        current_role = _ensure_role(user.role)

        return AuthenticatedPrincipal(
            user_id=user_id,
            role=current_role,
            token_type=ACCESS_TOKEN_TYPE,
            session_id=session_id,
            token_jti=token_jti or None,
        )

    def get_user_profile(self, user_id: str) -> AuthProfile:
        normalized_user_id = _normalize_text(user_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")

        user = self.repository.get_auth_user_by_user_id(normalized_user_id)
        if user is None:
            raise LookupError("auth user is not registered")
        return self._build_profile(user)

    def list_users(self, *, limit: int = 100) -> list[AuthProfile]:
        resolved_limit = max(1, min(int(limit), 500))
        users = self.repository.list_auth_users(limit=resolved_limit)
        return [self._build_profile(user) for user in users]

    def update_user(
        self,
        *,
        user_id: str,
        display_name: str | None = None,
        role: str | None = None,
        status: str | None = None,
    ) -> AuthUserUpdateResult:
        normalized_user_id = _normalize_text(user_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")

        normalized_display_name = _normalize_text(display_name) or None
        normalized_role = _ensure_role(role) if role is not None else None
        normalized_status = _ensure_status(status) if status is not None else None
        if (
            normalized_display_name is None
            and normalized_role is None
            and normalized_status is None
        ):
            raise ValueError("at least one auth user field must be updated")

        updated_user = self.repository.update_auth_user(
            user_id=normalized_user_id,
            display_name=normalized_display_name,
            role=normalized_role,
            status=normalized_status,
        )

        revoked_session_count = 0
        if normalized_status == "disabled":
            revoked_session_count = self.repository.revoke_refresh_sessions_by_user(
                user_id=normalized_user_id
            )

        return AuthUserUpdateResult(
            user=self._build_profile(updated_user),
            revoked_session_count=revoked_session_count,
        )

    def check_health(self) -> None:
        self.repository.check_health()


def build_default_auth_service() -> AuthService:
    jwt_secret = os.getenv("API_AUTH_JWT_SECRET", "").strip()
    if not jwt_secret:
        raise ValueError("API_AUTH_JWT_SECRET is required for auth service")

    access_ttl_sec = int(
        os.getenv("API_AUTH_ACCESS_TTL_SEC", "900").strip() or "900"
    )
    refresh_ttl_sec = int(
        os.getenv("API_AUTH_REFRESH_TTL_SEC", str(60 * 60 * 24 * 30)).strip()
        or str(60 * 60 * 24 * 30)
    )
    password_iterations = int(
        os.getenv("API_AUTH_PASSWORD_ITERATIONS", "600000").strip() or "600000"
    )

    return AuthService(
        repository=build_default_auth_store(),
        jwt_secret=jwt_secret,
        access_ttl_sec=access_ttl_sec,
        refresh_ttl_sec=refresh_ttl_sec,
        password_iterations=password_iterations,
    )
