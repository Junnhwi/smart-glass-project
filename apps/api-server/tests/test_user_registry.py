from __future__ import annotations

import unittest

from src.database.user_registry import DeviceRecord, PostgresUserRegistry, UserRecord


class FakeCursor:
    def __init__(
        self,
        row: tuple[object, ...] | None,
        rows: list[tuple[object, ...]] | None = None,
    ) -> None:
        self.row = row
        self.rows = rows or []
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, query: str, params: tuple[object, ...] | None = None) -> None:
        self.executed.append((query, params or ()))

    def fetchone(self) -> tuple[object, ...] | None:
        return self.row

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self.rows)

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.committed = False

    def cursor(self) -> FakeCursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True

    def __enter__(self) -> FakeConnection:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class PostgresUserRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = PostgresUserRegistry("postgresql://example")
        self.registry._schema_ready = True
        self.registry.get_user = lambda user_id: UserRecord(  # type: ignore[method-assign]
            user_id=user_id,
            created_at="2026-05-05T00:00:00Z",
        )

    def test_register_device_only_updates_same_existing_owner(self) -> None:
        cursor = FakeCursor(
            (
                "glass-001",
                "user-1",
                "active",
                "2026-05-05T00:01:00Z",
                "2026-05-05T00:01:00Z",
                None,
                "2026-05-05T00:01:00Z",
            )
        )
        connection = FakeConnection(cursor)
        self.registry._connect = lambda: connection  # type: ignore[method-assign]

        record = self.registry.register_device(user_id="user-1", device_id="glass-001")

        self.assertEqual(record.user_id, "user-1")
        self.assertEqual(record.device_id, "glass-001")
        self.assertEqual(record.status, "active")
        self.assertTrue(connection.committed)
        self.assertEqual(cursor.executed[0][1], ("glass-001", "user-1", "active"))
        normalized_query = " ".join(cursor.executed[0][0].split())
        self.assertIn("ON CONFLICT (device_id) DO UPDATE", normalized_query)
        self.assertIn("WHERE devices.user_id = EXCLUDED.user_id", normalized_query)

    def test_register_device_raises_conflict_when_atomic_upsert_returns_no_row(self) -> None:
        cursor = FakeCursor(None)
        self.registry._connect = lambda: FakeConnection(cursor)  # type: ignore[method-assign]

        with self.assertRaisesRegex(
            ValueError,
            "deviceId is already registered to another user",
        ):
            self.registry.register_device(user_id="user-2", device_id="glass-001")

    def test_revoke_device_updates_status_and_revoked_at(self) -> None:
        existing_device = DeviceRecord(
            device_id="glass-001",
            user_id="user-1",
            registered_at="2026-05-05T00:01:00Z",
            status="active",
            approved_at="2026-05-05T00:01:00Z",
        )
        self.registry.get_device = lambda device_id: existing_device  # type: ignore[method-assign]
        cursor = FakeCursor(
            (
                "glass-001",
                "user-1",
                "revoked",
                "2026-05-05T00:01:00Z",
                "2026-05-05T00:01:00Z",
                "2026-05-05T00:03:00Z",
                "2026-05-05T00:03:00Z",
            )
        )
        connection = FakeConnection(cursor)
        self.registry._connect = lambda: connection  # type: ignore[method-assign]

        record = self.registry.revoke_device(user_id="user-1", device_id="glass-001")

        self.assertEqual(record.status, "revoked")
        self.assertEqual(record.revoked_at, "2026-05-05T00:03:00Z")
        self.assertTrue(connection.committed)

    def test_list_devices_returns_all_rows_for_user(self) -> None:
        cursor = FakeCursor(
            None,
            rows=[
                (
                    "glass-001",
                    "user-1",
                    "active",
                    "2026-05-05T00:01:00Z",
                    "2026-05-05T00:01:00Z",
                    None,
                    "2026-05-05T00:01:00Z",
                ),
                (
                    "glass-002",
                    "user-1",
                    "revoked",
                    "2026-05-05T00:02:00Z",
                    "2026-05-05T00:02:00Z",
                    "2026-05-05T00:04:00Z",
                    "2026-05-05T00:04:00Z",
                ),
            ],
        )
        self.registry._connect = lambda: FakeConnection(cursor)  # type: ignore[method-assign]

        records = self.registry.list_devices(user_id="user-1")

        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].device_id, "glass-001")
        self.assertEqual(records[1].status, "revoked")


if __name__ == "__main__":
    unittest.main()
