from __future__ import annotations

import unittest

from src.database.auth_store import PostgresAuthStore


class ScriptedCursor:
    def __init__(self, fetchone_results: list[object | None]) -> None:
        self.fetchone_results = list(fetchone_results)
        self.executed: list[tuple[str, tuple[object, ...] | None]] = []

    def __enter__(self) -> ScriptedCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> None:
        self.executed.append((query, params))

    def fetchone(self):
        if not self.fetchone_results:
            return None
        return self.fetchone_results.pop(0)


class ScriptedConnection:
    def __init__(self, cursor: ScriptedCursor) -> None:
        self.cursor_instance = cursor
        self.committed = False

    def __enter__(self) -> ScriptedConnection:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def cursor(self) -> ScriptedCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True


class PostgresAuthStoreTests(unittest.TestCase):
    def test_create_auth_user_reports_duplicate_email_as_conflict(self) -> None:
        store = PostgresAuthStore("postgresql://example")
        store._ensure_schema = lambda: None  # type: ignore[method-assign]

        cursor = ScriptedCursor(
            [
                None,
                ("existing-user",),
            ]
        )
        connection = ScriptedConnection(cursor)
        store._connect = lambda: connection  # type: ignore[method-assign]

        with self.assertRaisesRegex(ValueError, "email is already registered"):
            store.create_auth_user(
                user_id="user-new",
                email="user@example.com",
                password_hash="hashed-password",
                display_name="User",
                role="user",
                status="active",
            )

        self.assertFalse(connection.committed)
        self.assertIn("ON CONFLICT DO NOTHING", cursor.executed[1][0])


if __name__ == "__main__":
    unittest.main()
