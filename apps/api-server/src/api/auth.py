from __future__ import annotations

import os
import secrets

from fastapi import HTTPException, Request, status


DEMO_AUTH_TOKEN_PREFIX = "demo-user:"
INTERNAL_SERVICE_TOKEN_HEADER = "X-Internal-Service-Token"
INTERNAL_SERVICE_TOKEN_ENV = "API_INTERNAL_SERVICE_TOKEN"


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


def resolve_authenticated_user(
    request: Request,
    claimed_user_id: str | None = None,
) -> str:
    authorization = request.headers.get("Authorization", "").strip()
    if not authorization:
        raise _unauthorized("Authorization header is required")

    scheme, _, credentials = authorization.partition(" ")
    if scheme.lower() != "bearer" or not credentials.strip():
        raise _unauthorized("Authorization header must use Bearer token")

    token = credentials.strip()
    if not token.startswith(DEMO_AUTH_TOKEN_PREFIX):
        raise _unauthorized("Unsupported authorization token")

    authenticated_user_id = token[len(DEMO_AUTH_TOKEN_PREFIX) :].strip()
    if not authenticated_user_id:
        raise _unauthorized("Authenticated user id is missing")

    if claimed_user_id is not None:
        normalized_claimed_user_id = claimed_user_id.strip()
        if (
            normalized_claimed_user_id
            and normalized_claimed_user_id != authenticated_user_id
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Requested user does not match authenticated user"
                ),
            )

    return authenticated_user_id


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
