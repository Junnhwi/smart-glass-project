from __future__ import annotations

import os

from src.database.auth_store import build_default_auth_store
from src.modules.auth.service import _hash_password


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} must be configured")
    return value


def main() -> None:
    email = _require_env("ADMIN_BOOTSTRAP_EMAIL").lower()
    password = _require_env("ADMIN_BOOTSTRAP_PASSWORD")
    user_id = os.getenv("ADMIN_BOOTSTRAP_USER_ID", "team-admin").strip() or "team-admin"
    display_name = (
        os.getenv("ADMIN_BOOTSTRAP_DISPLAY_NAME", "Team Admin").strip()
        or "Team Admin"
    )
    password_iterations = int(
        os.getenv("API_AUTH_PASSWORD_ITERATIONS", "600000").strip() or "600000"
    )
    password_hash = _hash_password(password, iterations=password_iterations)

    repository = build_default_auth_store()
    existing = repository.get_auth_user_by_email(email)
    if existing is None:
        repository.create_auth_user(
            user_id=user_id,
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            role="admin",
            status="active",
        )
        print(f"admin bootstrap created: {email}")
        return

    repository.update_auth_user(
        user_id=existing.user_id,
        password_hash=password_hash,
        display_name=display_name,
        role="admin",
        status="active",
    )
    revoked_sessions = repository.revoke_refresh_sessions_by_user(
        user_id=existing.user_id
    )
    print(f"admin bootstrap updated: {email}; revoked sessions: {revoked_sessions}")


if __name__ == "__main__":
    main()
