from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from src.database.user_registry import (
    DeviceRecord,
    UserRecord,
    build_default_user_registry,
)


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _ensure_identifier(prefix: str, explicit: str | None) -> str:
    normalized = _normalize_text(explicit)
    if normalized:
        return normalized
    return f"{prefix}-{uuid4().hex[:12]}"


@dataclass(frozen=True, slots=True)
class DeviceAuthorization:
    status: str
    device_id: str
    user_id: str | None = None


class UserDeviceRepository(Protocol):
    def create_user(self, user_id: str) -> UserRecord: ...

    def get_user(self, user_id: str) -> UserRecord | None: ...

    def register_device(self, *, user_id: str, device_id: str) -> DeviceRecord: ...

    def get_device(self, device_id: str) -> DeviceRecord | None: ...

    def find_user_by_device_id(self, device_id: str) -> UserRecord | None: ...

    def check_health(self) -> None: ...


class UserDeviceService:
    def __init__(self, repository: UserDeviceRepository) -> None:
        self.repository = repository

    def create_user(self, *, user_id: str | None = None) -> UserRecord:
        resolved_user_id = _ensure_identifier("user", user_id)
        return self.repository.create_user(resolved_user_id)

    def register_device(self, *, user_id: str, device_id: str) -> DeviceRecord:
        normalized_user_id = _normalize_text(user_id)
        normalized_device_id = _normalize_text(device_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_device_id:
            raise ValueError("deviceId must not be blank")
        return self.repository.register_device(
            user_id=normalized_user_id,
            device_id=normalized_device_id,
        )

    def authorize_device(self, *, device_id: str) -> DeviceAuthorization:
        normalized_device_id = _normalize_text(device_id)
        if not normalized_device_id:
            raise ValueError("deviceId must not be blank")

        user = self.repository.find_user_by_device_id(normalized_device_id)
        if user is None:
            return DeviceAuthorization(
                status="blocked",
                device_id=normalized_device_id,
                user_id=None,
            )
        return DeviceAuthorization(
            status="allowed",
            device_id=normalized_device_id,
            user_id=user.user_id,
        )

    def check_health(self) -> None:
        self.repository.check_health()


def build_default_user_device_service() -> UserDeviceService:
    return UserDeviceService(repository=build_default_user_registry())
