from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.bootstrap_admin import main
from src.database.auth_store import AuthUserRecord


class FakeAuthStore:
    def __init__(self, existing: AuthUserRecord | None = None) -> None:
        self.existing = existing
        self.created: dict[str, object] | None = None
        self.updated: dict[str, object] | None = None
        self.revoked_user_id: str | None = None

    def get_auth_user_by_email(self, email: str) -> AuthUserRecord | None:
        if self.existing is None or self.existing.email != email:
            return None
        return self.existing

    def create_auth_user(self, **kwargs: object) -> None:
        self.created = kwargs

    def update_auth_user(self, **kwargs: object) -> None:
        self.updated = kwargs

    def revoke_refresh_sessions_by_user(self, *, user_id: str) -> int:
        self.revoked_user_id = user_id
        return 2


class BootstrapAdminTest(unittest.TestCase):
    def _run(self, repository: FakeAuthStore) -> None:
        with (
            patch.dict(
                "os.environ",
                {
                    "ADMIN_BOOTSTRAP_EMAIL": "Admin@Example.com",
                    "ADMIN_BOOTSTRAP_PASSWORD": "new-password",
                    "ADMIN_BOOTSTRAP_USER_ID": "bootstrap-admin",
                    "ADMIN_BOOTSTRAP_DISPLAY_NAME": "Bootstrap Admin",
                    "API_AUTH_PASSWORD_ITERATIONS": "1234",
                },
                clear=True,
            ),
            patch(
                "scripts.bootstrap_admin.build_default_auth_store",
                return_value=repository,
            ),
            patch(
                "scripts.bootstrap_admin._hash_password",
                return_value="hashed-password",
            ) as hash_password,
        ):
            main()

        hash_password.assert_called_once_with("new-password", iterations=1234)

    def test_creates_active_admin_when_email_is_new(self) -> None:
        repository = FakeAuthStore()

        self._run(repository)

        self.assertEqual(
            repository.created,
            {
                "user_id": "bootstrap-admin",
                "email": "admin@example.com",
                "password_hash": "hashed-password",
                "display_name": "Bootstrap Admin",
                "role": "admin",
                "status": "active",
            },
        )
        self.assertIsNone(repository.updated)
        self.assertIsNone(repository.revoked_user_id)

    def test_updates_existing_admin_and_revokes_refresh_sessions(self) -> None:
        repository = FakeAuthStore(
            AuthUserRecord(
                user_id="existing-admin",
                email="admin@example.com",
                password_hash="old-password-hash",
                display_name="Old Admin",
                role="user",
                status="disabled",
                created_at="2026-05-30T00:00:00Z",
                last_login_at=None,
            )
        )

        self._run(repository)

        self.assertEqual(
            repository.updated,
            {
                "user_id": "existing-admin",
                "password_hash": "hashed-password",
                "display_name": "Bootstrap Admin",
                "role": "admin",
                "status": "active",
            },
        )
        self.assertIsNone(repository.created)
        self.assertEqual(repository.revoked_user_id, "existing-admin")

    def test_requires_password(self) -> None:
        with patch.dict(
            "os.environ",
            {"ADMIN_BOOTSTRAP_EMAIL": "admin@example.com"},
            clear=True,
        ):
            with self.assertRaisesRegex(
                RuntimeError, "ADMIN_BOOTSTRAP_PASSWORD must be configured"
            ):
                main()


if __name__ == "__main__":
    unittest.main()
