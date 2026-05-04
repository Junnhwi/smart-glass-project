from __future__ import annotations

import unittest

from src.database.user_registry import DeviceRecord, UserRecord
from src.modules.users.service import UserDeviceService


class FakeUserDeviceRepository:
    def __init__(self) -> None:
        self.users: dict[str, UserRecord] = {}
        self.devices: dict[str, DeviceRecord] = {}
        self.health_checked = False

    def create_user(self, user_id: str) -> UserRecord:
        record = self.users.get(user_id)
        if record is None:
            record = UserRecord(
                user_id=user_id,
                created_at="2026-05-05T00:00:00Z",
            )
            self.users[user_id] = record
        return record

    def get_user(self, user_id: str) -> UserRecord | None:
        return self.users.get(user_id)

    def register_device(self, *, user_id: str, device_id: str) -> DeviceRecord:
        if user_id not in self.users:
            raise LookupError("userId is not registered")
        existing_device = self.devices.get(device_id)
        if existing_device is not None and existing_device.user_id != user_id:
            raise ValueError("deviceId is already registered to another user")
        record = DeviceRecord(
            device_id=device_id,
            user_id=user_id,
            registered_at="2026-05-05T00:01:00Z",
        )
        self.devices[device_id] = record
        return record

    def get_device(self, device_id: str) -> DeviceRecord | None:
        return self.devices.get(device_id)

    def find_user_by_device_id(self, device_id: str) -> UserRecord | None:
        device = self.devices.get(device_id)
        if device is None:
            return None
        return self.users.get(device.user_id)

    def check_health(self) -> None:
        self.health_checked = True


class UserDeviceServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeUserDeviceRepository()
        self.service = UserDeviceService(self.repository)

    def test_create_user_generates_identifier_when_missing(self) -> None:
        record = self.service.create_user()

        self.assertTrue(record.user_id.startswith("user-"))
        self.assertEqual(record.created_at, "2026-05-05T00:00:00Z")
        self.assertEqual(self.repository.get_user(record.user_id), record)

    def test_create_user_preserves_explicit_identifier(self) -> None:
        record = self.service.create_user(user_id=" user-1 ")

        self.assertEqual(record.user_id, "user-1")
        self.assertEqual(self.repository.get_user("user-1"), record)

    def test_register_device_links_device_to_existing_user(self) -> None:
        self.service.create_user(user_id="user-1")

        record = self.service.register_device(
            user_id=" user-1 ",
            device_id=" glass-001 ",
        )

        self.assertEqual(record.user_id, "user-1")
        self.assertEqual(record.device_id, "glass-001")
        self.assertEqual(self.repository.get_device("glass-001"), record)

    def test_register_device_rejects_unknown_user(self) -> None:
        with self.assertRaisesRegex(LookupError, "userId is not registered"):
            self.service.register_device(user_id="user-404", device_id="glass-404")

    def test_register_device_rejects_reassignment_to_another_user(self) -> None:
        self.service.create_user(user_id="user-1")
        self.service.create_user(user_id="user-2")
        self.service.register_device(user_id="user-1", device_id="glass-001")

        with self.assertRaisesRegex(
            ValueError,
            "deviceId is already registered to another user",
        ):
            self.service.register_device(user_id="user-2", device_id="glass-001")

    def test_authorize_device_returns_allowed_for_registered_device(self) -> None:
        self.service.create_user(user_id="user-1")
        self.service.register_device(user_id="user-1", device_id="glass-001")

        result = self.service.authorize_device(device_id=" glass-001 ")

        self.assertEqual(result.status, "allowed")
        self.assertEqual(result.user_id, "user-1")
        self.assertEqual(result.device_id, "glass-001")

    def test_authorize_device_returns_blocked_for_unknown_device(self) -> None:
        result = self.service.authorize_device(device_id="glass-999")

        self.assertEqual(result.status, "blocked")
        self.assertIsNone(result.user_id)
        self.assertEqual(result.device_id, "glass-999")

    def test_health_check_delegates_to_repository(self) -> None:
        self.service.check_health()

        self.assertTrue(self.repository.health_checked)


if __name__ == "__main__":
    unittest.main()
