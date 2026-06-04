from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import secrets
from typing import Protocol
from uuid import uuid4

from src.database.user_registry import (
    DeviceRecord,
    DevicePairingRecord,
    MemoryQueryLogRecord,
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


@dataclass(frozen=True, slots=True)
class CaptureEventResult:
    device: DeviceRecord
    should_capture: bool
    reason: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ensure_device_status(value: str | None) -> str:
    normalized = _normalize_text(value) or "active"
    if normalized not in {"active", "revoked"}:
        raise ValueError("device status must be one of: active, revoked")
    return normalized


class UserDeviceRepository(Protocol):
    def create_user(self, user_id: str) -> UserRecord: ...

    def get_user(self, user_id: str) -> UserRecord | None: ...

    def register_device(self, *, user_id: str, device_id: str) -> DeviceRecord: ...

    def get_device(self, device_id: str) -> DeviceRecord | None: ...

    def list_devices(self, *, user_id: str) -> list[DeviceRecord]: ...

    def update_device_display_name(
        self,
        *,
        user_id: str,
        device_id: str,
        display_name: str,
    ) -> DeviceRecord: ...

    def issue_pairing_code(
        self,
        *,
        user_id: str,
        device_id: str,
        pairing_code: str,
        expires_in_minutes: int,
    ) -> DevicePairingRecord: ...

    def get_pairing_code(self, pairing_code: str) -> DevicePairingRecord | None: ...

    def list_pairing_codes(
        self,
        *,
        user_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[DevicePairingRecord]: ...

    def update_pairing_status(
        self,
        *,
        pairing_code: str,
        status: str,
        approved: bool = False,
    ) -> DevicePairingRecord: ...

    def record_memory_query_log(
        self,
        *,
        user_id: str,
        query_type: str,
        query_text: str,
        total_hits: int,
        answer_text: str | None = None,
        answer_mode: str | None = None,
        cited_memory_ids_json: str | None = None,
    ) -> MemoryQueryLogRecord: ...

    def list_memory_query_logs(
        self,
        *,
        user_id: str | None = None,
        query_type: str | None = None,
        limit: int = 100,
    ) -> list[MemoryQueryLogRecord]: ...

    def approve_device(self, *, user_id: str, device_id: str) -> DeviceRecord: ...

    def revoke_device(self, *, user_id: str, device_id: str) -> DeviceRecord: ...

    def update_device_capture_control(
        self,
        *,
        user_id: str,
        device_id: str,
        enabled: bool,
        interval_sec: int,
    ) -> DeviceRecord: ...

    def record_device_capture_event(
        self,
        *,
        user_id: str,
        device_id: str,
        event_type: str,
        interval_sec: int,
    ) -> DeviceRecord | None: ...

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

    def list_devices(self, *, user_id: str) -> list[DeviceRecord]:
        normalized_user_id = _normalize_text(user_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        return self.repository.list_devices(user_id=normalized_user_id)

    def update_device_display_name(
        self,
        *,
        user_id: str,
        device_id: str,
        display_name: str,
    ) -> DeviceRecord:
        normalized_user_id = _normalize_text(user_id)
        normalized_device_id = _normalize_text(device_id)
        normalized_display_name = _normalize_text(display_name)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_device_id:
            raise ValueError("deviceId must not be blank")
        if not normalized_display_name:
            raise ValueError("displayName must not be blank")
        return self.repository.update_device_display_name(
            user_id=normalized_user_id,
            device_id=normalized_device_id,
            display_name=normalized_display_name,
        )

    def issue_pairing_code(
        self,
        *,
        user_id: str,
        device_id: str,
        expires_in_minutes: int = 10,
    ) -> DevicePairingRecord:
        normalized_user_id = _normalize_text(user_id)
        normalized_device_id = _normalize_text(device_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_device_id:
            raise ValueError("deviceId must not be blank")

        for _ in range(5):
            pairing_code = secrets.token_hex(3).upper()
            try:
                return self.repository.issue_pairing_code(
                    user_id=normalized_user_id,
                    device_id=normalized_device_id,
                    pairing_code=pairing_code,
                    expires_in_minutes=expires_in_minutes,
                )
            except Exception as exc:
                if "duplicate key value" not in str(exc).lower():
                    raise

        raise RuntimeError("failed to generate a unique pairing code")

    def list_pairing_codes(
        self,
        *,
        user_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[DevicePairingRecord]:
        normalized_user_id = _normalize_text(user_id)
        normalized_status = _normalize_text(status).lower() or None
        return self.repository.list_pairing_codes(
            user_id=normalized_user_id or None,
            status=normalized_status,
            limit=limit,
        )

    def approve_pairing_code(self, *, pairing_code: str) -> DevicePairingRecord:
        pairing = self._require_active_pairing(pairing_code)
        self.repository.register_device(
            user_id=pairing.user_id,
            device_id=pairing.device_id,
        )
        return self.repository.update_pairing_status(
            pairing_code=pairing.pairing_code,
            status="approved",
            approved=True,
        )

    def reject_pairing_code(self, *, pairing_code: str) -> DevicePairingRecord:
        pairing = self._require_active_pairing(pairing_code)
        return self.repository.update_pairing_status(
            pairing_code=pairing.pairing_code,
            status="rejected",
            approved=False,
        )

    def approve_device(self, *, user_id: str, device_id: str) -> DeviceRecord:
        normalized_user_id = _normalize_text(user_id)
        normalized_device_id = _normalize_text(device_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_device_id:
            raise ValueError("deviceId must not be blank")
        return self.repository.approve_device(
            user_id=normalized_user_id,
            device_id=normalized_device_id,
        )

    def revoke_device(self, *, user_id: str, device_id: str) -> DeviceRecord:
        normalized_user_id = _normalize_text(user_id)
        normalized_device_id = _normalize_text(device_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_device_id:
            raise ValueError("deviceId must not be blank")
        return self.repository.revoke_device(
            user_id=normalized_user_id,
            device_id=normalized_device_id,
        )

    def get_capture_control(self, *, user_id: str, device_id: str) -> DeviceRecord:
        return self._require_owned_active_device(
            user_id=user_id,
            device_id=device_id,
        )

    def update_capture_control(
        self,
        *,
        user_id: str,
        device_id: str,
        enabled: bool,
        interval_sec: int | None = None,
    ) -> DeviceRecord:
        device = self._require_owned_active_device(
            user_id=user_id,
            device_id=device_id,
        )
        resolved_interval_sec = (
            int(interval_sec)
            if interval_sec is not None
            else int(device.capture_interval_sec or 300)
        )
        if resolved_interval_sec < 60:
            raise ValueError("intervalSec must be greater than or equal to 60")
        if resolved_interval_sec > 86400:
            raise ValueError("intervalSec must be less than or equal to 86400")
        return self.repository.update_device_capture_control(
            user_id=device.user_id,
            device_id=device.device_id,
            enabled=enabled,
            interval_sec=resolved_interval_sec,
        )

    def record_capture_event(
        self,
        *,
        user_id: str,
        device_id: str,
        event_type: str,
    ) -> CaptureEventResult:
        normalized_event_type = _normalize_text(event_type)
        if normalized_event_type not in {"start_capture", "scheduled_capture"}:
            raise ValueError("eventType must be one of: start_capture, scheduled_capture")

        device = self._require_owned_active_device(
            user_id=user_id,
            device_id=device_id,
        )
        if not device.capture_enabled:
            return CaptureEventResult(
                device=device,
                should_capture=False,
                reason="disabled",
            )

        interval_sec = int(device.capture_interval_sec or 300)
        if normalized_event_type == "scheduled_capture" and device.capture_last_event_at:
            last_event_at = _parse_timestamp(device.capture_last_event_at)
            next_event_at = last_event_at + timedelta(seconds=interval_sec)
            if _utc_now() < next_event_at:
                return CaptureEventResult(
                    device=device,
                    should_capture=False,
                    reason="interval_not_elapsed",
                )

        updated_device = self.repository.record_device_capture_event(
            user_id=device.user_id,
            device_id=device.device_id,
            event_type=normalized_event_type,
            interval_sec=interval_sec,
        )
        if updated_device is None:
            latest_device = self.repository.get_device(device.device_id)
            if latest_device is not None and latest_device.user_id == device.user_id:
                device = latest_device
            return CaptureEventResult(
                device=device,
                should_capture=False,
                reason="interval_not_elapsed",
            )
        return CaptureEventResult(
            device=updated_device,
            should_capture=True,
            reason="accepted",
        )

    def authorize_device(self, *, device_id: str) -> DeviceAuthorization:
        normalized_device_id = _normalize_text(device_id)
        if not normalized_device_id:
            raise ValueError("deviceId must not be blank")

        device = self.repository.get_device(normalized_device_id)
        if device is None:
            return DeviceAuthorization(
                status="blocked",
                device_id=normalized_device_id,
                user_id=None,
            )
        if _ensure_device_status(device.status) != "active":
            return DeviceAuthorization(
                status="blocked",
                device_id=normalized_device_id,
                user_id=None,
            )
        return DeviceAuthorization(
            status="allowed",
            device_id=normalized_device_id,
            user_id=device.user_id,
        )

    def record_memory_query_log(
        self,
        *,
        user_id: str,
        query_type: str,
        query_text: str,
        total_hits: int,
        answer_text: str | None = None,
        answer_mode: str | None = None,
        cited_memory_ids_json: str | None = None,
    ) -> MemoryQueryLogRecord:
        normalized_user_id = _normalize_text(user_id)
        normalized_query_type = _normalize_text(query_type).lower()
        normalized_query_text = _normalize_text(query_text)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_query_text:
            raise ValueError("queryText must not be blank")
        return self.repository.record_memory_query_log(
            user_id=normalized_user_id,
            query_type=normalized_query_type,
            query_text=normalized_query_text,
            total_hits=total_hits,
            answer_text=answer_text,
            answer_mode=answer_mode,
            cited_memory_ids_json=cited_memory_ids_json,
        )

    def list_memory_query_logs(
        self,
        *,
        user_id: str | None = None,
        query_type: str | None = None,
        limit: int = 100,
    ) -> list[MemoryQueryLogRecord]:
        return self.repository.list_memory_query_logs(
            user_id=_normalize_text(user_id) or None,
            query_type=_normalize_text(query_type).lower() or None,
            limit=limit,
        )

    def _require_active_pairing(self, pairing_code: str) -> DevicePairingRecord:
        normalized_pairing_code = _normalize_text(pairing_code).upper()
        if not normalized_pairing_code:
            raise ValueError("pairingCode must not be blank")

        pairing = self.repository.get_pairing_code(normalized_pairing_code)
        if pairing is None:
            raise LookupError("pairingCode is not registered")
        if pairing.status != "pending":
            raise ValueError("pairingCode is no longer pending")
        if _parse_timestamp(pairing.expires_at) <= _utc_now():
            self.repository.update_pairing_status(
                pairing_code=pairing.pairing_code,
                status="rejected",
                approved=False,
            )
            raise PermissionError("pairingCode has expired")
        return pairing

    def _require_owned_active_device(
        self,
        *,
        user_id: str,
        device_id: str,
    ) -> DeviceRecord:
        normalized_user_id = _normalize_text(user_id)
        normalized_device_id = _normalize_text(device_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_device_id:
            raise ValueError("deviceId must not be blank")

        device = self.repository.get_device(normalized_device_id)
        if device is None:
            raise LookupError("deviceId is not registered")
        if device.user_id != normalized_user_id:
            raise PermissionError("deviceId does not match requested userId")
        if _ensure_device_status(device.status) != "active":
            raise PermissionError("deviceId is not active")
        return device

    def check_health(self) -> None:
        self.repository.check_health()


def build_default_user_device_service() -> UserDeviceService:
    return UserDeviceService(repository=build_default_user_registry())
