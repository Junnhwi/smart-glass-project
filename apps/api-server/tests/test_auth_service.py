from __future__ import annotations

import unittest

from src.database.auth_store import AuthSessionRecord, AuthUserRecord
from src.modules.auth.service import AuthService, _hash_refresh_token


class FakeAuthRepository:
    def __init__(self) -> None:
        self.users_by_email: dict[str, AuthUserRecord] = {}
        self.users_by_user_id: dict[str, AuthUserRecord] = {}
        self.sessions_by_hash: dict[str, AuthSessionRecord] = {}
        self.revoked_token_jtis: set[str] = set()
        self.revoked_sessions_by_user: dict[str, int] = {}
        self.health_checked = False

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
        if user_id in self.users_by_user_id:
            raise ValueError("userId is already registered for sign-in")
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
        self.users_by_user_id[user_id] = record
        return record

    def get_auth_user_by_email(self, email: str) -> AuthUserRecord | None:
        return self.users_by_email.get(email)

    def get_auth_user_by_user_id(self, user_id: str) -> AuthUserRecord | None:
        return self.users_by_user_id.get(user_id)

    def list_auth_users(self, *, limit: int = 100) -> list[AuthUserRecord]:
        return list(self.users_by_user_id.values())[:limit]

    def update_auth_user(
        self,
        *,
        user_id: str,
        display_name: str | None = None,
        role: str | None = None,
        status: str | None = None,
    ) -> AuthUserRecord:
        record = self.users_by_user_id.get(user_id)
        if record is None:
            raise LookupError("auth user is not registered")
        updated_record = AuthUserRecord(
            user_id=record.user_id,
            email=record.email,
            password_hash=record.password_hash,
            display_name=display_name if display_name is not None else record.display_name,
            role=role if role is not None else record.role,
            status=status if status is not None else record.status,
            created_at=record.created_at,
            last_login_at=record.last_login_at,
        )
        self.users_by_user_id[user_id] = updated_record
        self.users_by_email[record.email] = updated_record
        return updated_record

    def touch_last_login(self, user_id: str) -> AuthUserRecord:
        record = self.users_by_user_id[user_id]
        updated_record = AuthUserRecord(
            user_id=record.user_id,
            email=record.email,
            password_hash=record.password_hash,
            display_name=record.display_name,
            role=record.role,
            status=record.status,
            created_at=record.created_at,
            last_login_at="2026-05-05T00:10:00Z",
        )
        self.users_by_user_id[user_id] = updated_record
        self.users_by_email[record.email] = updated_record
        return updated_record

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
    ) -> AuthSessionRecord:
        session = AuthSessionRecord(
            session_id=session_id,
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            device_id=device_id,
            user_agent=user_agent,
            ip_address=ip_address,
            created_at="2026-05-05T00:10:00Z",
            expires_at=expires_at,
            revoked_at=None,
            replaced_by_session_id=None,
        )
        self.sessions_by_hash[refresh_token_hash] = session
        return session

    def get_refresh_session_by_token_hash(
        self,
        refresh_token_hash: str,
    ) -> AuthSessionRecord | None:
        return self.sessions_by_hash.get(refresh_token_hash)

    def revoke_refresh_session(
        self,
        *,
        session_id: str,
        replaced_by_session_id: str | None = None,
    ) -> bool:
        for session_hash, session in list(self.sessions_by_hash.items()):
            if session.session_id != session_id:
                continue
            self.sessions_by_hash[session_hash] = AuthSessionRecord(
                session_id=session.session_id,
                user_id=session.user_id,
                refresh_token_hash=session.refresh_token_hash,
                device_id=session.device_id,
                user_agent=session.user_agent,
                ip_address=session.ip_address,
                created_at=session.created_at,
                expires_at=session.expires_at,
                revoked_at="2026-05-05T00:20:00Z",
                replaced_by_session_id=replaced_by_session_id,
            )
            return True
        return False

    def revoke_refresh_sessions_by_user(self, *, user_id: str) -> int:
        count = 0
        for session_hash, session in list(self.sessions_by_hash.items()):
            if session.user_id != user_id or session.revoked_at is not None:
                continue
            self.sessions_by_hash[session_hash] = AuthSessionRecord(
                session_id=session.session_id,
                user_id=session.user_id,
                refresh_token_hash=session.refresh_token_hash,
                device_id=session.device_id,
                user_agent=session.user_agent,
                ip_address=session.ip_address,
                created_at=session.created_at,
                expires_at=session.expires_at,
                revoked_at="2026-05-05T00:30:00Z",
                replaced_by_session_id=session.replaced_by_session_id,
            )
            count += 1
        self.revoked_sessions_by_user[user_id] = count
        return count

    def revoke_access_token(
        self,
        *,
        jti: str,
        user_id: str,
        expires_at: str,
    ) -> bool:
        self.revoked_token_jtis.add(jti)
        return True

    def is_access_token_revoked(self, jti: str) -> bool:
        return jti in self.revoked_token_jtis

    def check_health(self) -> None:
        self.health_checked = True


class AuthServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeAuthRepository()
        self.service = AuthService(
            self.repository,
            jwt_secret="test-secret",
            access_ttl_sec=900,
            refresh_ttl_sec=3600,
            password_iterations=100_000,
        )

    def test_sign_up_creates_user_and_returns_tokens(self) -> None:
        bundle = self.service.sign_up(
            email="User@example.com",
            password="password123",
            display_name="Test User",
        )

        self.assertEqual(bundle.user.email, "user@example.com")
        self.assertEqual(bundle.user.display_name, "Test User")
        self.assertEqual(bundle.user.role, "user")
        self.assertTrue(bundle.access_token)
        self.assertTrue(bundle.refresh_token)
        stored_user = self.repository.get_auth_user_by_email("user@example.com")
        self.assertIsNotNone(stored_user)
        self.assertNotEqual(stored_user.password_hash, "password123")

    def test_login_rejects_invalid_password(self) -> None:
        self.service.sign_up(
            email="user@example.com",
            password="password123",
            display_name="Test User",
        )

        with self.assertRaisesRegex(PermissionError, "Invalid email or password"):
            self.service.login(
                email="user@example.com",
                password="wrong-password",
            )

    def test_refresh_rotates_session_and_revokes_previous_refresh_token(self) -> None:
        bundle = self.service.sign_up(
            email="user@example.com",
            password="password123",
        )

        next_bundle = self.service.refresh(refresh_token=bundle.refresh_token)

        self.assertNotEqual(next_bundle.refresh_token, bundle.refresh_token)
        old_session = self.repository.get_refresh_session_by_token_hash(
            _hash_refresh_token(bundle.refresh_token)
        )
        self.assertIsNotNone(old_session)
        self.assertEqual(old_session.revoked_at, "2026-05-05T00:20:00Z")
        next_session = self.repository.get_refresh_session_by_token_hash(
            _hash_refresh_token(next_bundle.refresh_token)
        )
        self.assertIsNotNone(next_session)
        self.assertIsNone(next_session.revoked_at)

    def test_logout_revokes_access_and_refresh_tokens(self) -> None:
        bundle = self.service.sign_up(
            email="user@example.com",
            password="password123",
        )

        outcome = self.service.logout(
            refresh_token=bundle.refresh_token,
            access_token=bundle.access_token,
        )

        self.assertTrue(outcome.revoked_refresh_token)
        self.assertTrue(outcome.revoked_access_token)
        with self.assertRaisesRegex(PermissionError, "revoked"):
            self.service.authenticate_access_token(bundle.access_token)

    def test_check_health_delegates_to_repository(self) -> None:
        self.service.check_health()

        self.assertTrue(self.repository.health_checked)

    def test_list_users_returns_profiles(self) -> None:
        self.service.sign_up(
            email="user@example.com",
            password="password123",
            display_name="Test User",
        )

        users = self.service.list_users(limit=10)

        self.assertEqual(len(users), 1)
        self.assertEqual(users[0].email, "user@example.com")

    def test_update_user_disables_account_and_revokes_sessions(self) -> None:
        bundle = self.service.sign_up(
            email="user@example.com",
            password="password123",
            display_name="Test User",
        )

        result = self.service.update_user(
            user_id=bundle.user.user_id,
            role="admin",
            status="disabled",
        )

        self.assertEqual(result.user.role, "admin")
        self.assertEqual(result.user.status, "disabled")
        self.assertEqual(result.revoked_session_count, 1)


if __name__ == "__main__":
    unittest.main()
