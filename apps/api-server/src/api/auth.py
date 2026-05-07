from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status


DEMO_AUTH_TOKEN_PREFIX = "demo-user:"
INTERNAL_SERVICE_TOKEN_HEADER = "X-Internal-Service-Token"
INTERNAL_SERVICE_TOKEN_ENV = "API_INTERNAL_SERVICE_TOKEN"
ENABLE_DEMO_TOKENS_ENV = "API_AUTH_ENABLE_DEMO_TOKENS"


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    user_id: str
    role: str
    token_type: str
    session_id: str | None = None
    token_jti: str | None = None


def build_demo_auth_token(user_id: str) -> str:
    normalized = str(user_id).strip()
    if not normalized:
        raise ValueError("user_id is required")
    return f"{DEMO_AUTH_TOKEN_PREFIX}{normalized}"


def build_bearer_authorization_header(user_id: str) -> str:
    return f"Bearer {build_demo_auth_token(user_id)}"


def build_internal_service_token() -> str:
    token = os.getenv(INTERNAL_SERVICE_TOKEN_ENV, "").strip()
    if not token:
        raise RuntimeError(f"{INTERNAL_SERVICE_TOKEN_ENV} must be configured")
    return token


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _demo_tokens_enabled() -> bool:
    raw_value = os.getenv(ENABLE_DEMO_TOKENS_ENV, "1").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _get_auth_service(request: Request):
    auth_service = getattr(request.app.state, "auth_service", None)
    if auth_service is not None:
        return auth_service

    factory = getattr(request.app.state, "auth_service_factory", None)
    if factory is None:
        return None

    auth_service = factory()
    request.app.state.auth_service = auth_service
    return auth_service


def resolve_authenticated_principal(
    request: Request,
    claimed_user_id: str | None = None,
    *,
    allowed_roles: set[str] | None = None,
) -> AuthenticatedPrincipal:
    authorization = request.headers.get("Authorization", "").strip()
    if not authorization:
        raise _unauthorized("Authorization header is required")

    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials.strip():
        raise _unauthorized("Authorization header must use Bearer token")

    token = credentials.strip()
    principal: AuthenticatedPrincipal
    if token.startswith(DEMO_AUTH_TOKEN_PREFIX):
        if not _demo_tokens_enabled():
            raise _unauthorized("Demo authorization tokens are disabled")

        authenticated_user_id = token[len(DEMO_AUTH_TOKEN_PREFIX) :].strip()
        if not authenticated_user_id:
            raise _unauthorized("Authenticated user id is missing")
        principal = AuthenticatedPrincipal(
            user_id=authenticated_user_id,
            role="user",
            token_type="demo",
        )
    else:
        try:
            auth_service = _get_auth_service(request)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        if auth_service is None:
            raise _unauthorized("Unsupported authorization token")

        try:
            principal = auth_service.authenticate_access_token(token)
        except PermissionError as exc:
            raise _unauthorized(str(exc)) from exc
        except LookupError as exc:
            raise _unauthorized(str(exc)) from exc
        except ValueError as exc:
            raise _unauthorized(str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

    if claimed_user_id is not None:
        normalized_claimed_user_id = claimed_user_id.strip()
        if (
            normalized_claimed_user_id
            and normalized_claimed_user_id != principal.user_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Requested user does not match authenticated user"
                ),
            )

    if allowed_roles is not None and principal.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authenticated user does not have the required role",
        )

    return principal


def resolve_authenticated_user(
    request: Request,
    claimed_user_id: str | None = None,
) -> str:
    principal = resolve_authenticated_principal(
        request,
        claimed_user_id=claimed_user_id,
    )
    return _normalize_text(principal.user_id)


def require_internal_service_token(request: Request) -> None:
    try:
        expected_token = build_internal_service_token()
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    provided_token = request.headers.get(
        INTERNAL_SERVICE_TOKEN_HEADER,
        "",
    ).strip()

    if not provided_token or not secrets.compare_digest(
        provided_token,
        expected_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid internal service token",
        )
