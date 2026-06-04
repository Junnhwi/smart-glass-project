from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

try:  # pragma: no cover - optional runtime dependency
    import psycopg
except ImportError:  # pragma: no cover - handled at runtime
    psycopg = None


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _normalize_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        parsed = value
    else:
        normalized = _normalize_text(value)
        if not normalized:
            parsed = datetime.now(timezone.utc)
        else:
            candidate = normalized.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(candidate)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return (
        parsed.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True, slots=True)
class UserRecord:
    user_id: str
    created_at: str


@dataclass(frozen=True, slots=True)
class DeviceRecord:
    device_id: str
    user_id: str
    registered_at: str
    status: str = "active"
    display_name: str | None = None
    approved_at: str | None = None
    revoked_at: str | None = None
    updated_at: str | None = None
    capture_enabled: bool = False
    capture_interval_sec: int = 300
    capture_updated_at: str | None = None
    capture_last_event_at: str | None = None


@dataclass(frozen=True, slots=True)
class DevicePairingRecord:
    pairing_code: str
    user_id: str
    device_id: str
    status: str
    created_at: str
    expires_at: str
    approved_at: str | None = None
    updated_at: str | None = None


@dataclass(frozen=True, slots=True)
class MemoryQueryLogRecord:
    log_id: int
    user_id: str
    query_type: str
    query_text: str
    total_hits: int
    answer_text: str | None = None
    answer_mode: str | None = None
    cited_memory_ids_json: str | None = None
    created_at: str = ""


class UserRegistryUnavailableError(RuntimeError):
    pass


class PostgresUserRegistry:
    users_table_name = "users"
    devices_table_name = "devices"
    device_pairings_table_name = "device_pairings"
    memory_query_logs_table_name = "memory_query_logs"
    active_device_status = "active"
    revoked_device_status = "revoked"
    pairing_pending_status = "pending"
    pairing_approved_status = "approved"
    pairing_rejected_status = "rejected"

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url.strip()
        if not self.database_url:
            raise ValueError("database_url must not be blank")
        self._lock = Lock()
        self._schema_ready = False

    def _require_driver(self) -> None:
        if psycopg is None:
            raise RuntimeError(
                "psycopg is required for api-server user/device storage. "
                "Install apps/api-server requirements."
            )

    def _connect(self):  # type: ignore[no-untyped-def]
        self._require_driver()
        try:
            return psycopg.connect(self.database_url)
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres connection failed: {exc}"
            ) from exc

    def _ensure_schema(self) -> None:
        if self._schema_ready:
            return

        with self._lock:
            if self._schema_ready:
                return

            try:
                with self._connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            f"""
                            CREATE TABLE IF NOT EXISTS {self.users_table_name} (
                                user_id TEXT PRIMARY KEY,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            )
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE TABLE IF NOT EXISTS {self.devices_table_name} (
                                device_id TEXT PRIMARY KEY,
                                user_id TEXT NOT NULL REFERENCES {self.users_table_name} (user_id),
                                status TEXT NOT NULL DEFAULT '{self.active_device_status}',
                                display_name TEXT,
                                approved_at TIMESTAMPTZ,
                                revoked_at TIMESTAMPTZ,
                                capture_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                                capture_interval_sec INTEGER NOT NULL DEFAULT 300,
                                capture_updated_at TIMESTAMPTZ,
                                capture_last_event_at TIMESTAMPTZ,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            )
                            """
                        )
                        cur.execute(
                            f"""
                            ALTER TABLE {self.devices_table_name}
                            ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT '{self.active_device_status}'
                            """
                        )
                        cur.execute(
                            f"""
                            ALTER TABLE {self.devices_table_name}
                            ADD COLUMN IF NOT EXISTS display_name TEXT
                            """
                        )
                        cur.execute(
                            f"""
                            ALTER TABLE {self.devices_table_name}
                            ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ
                            """
                        )
                        cur.execute(
                            f"""
                            ALTER TABLE {self.devices_table_name}
                            ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ
                            """
                        )
                        cur.execute(
                            f"""
                            ALTER TABLE {self.devices_table_name}
                            ADD COLUMN IF NOT EXISTS capture_enabled BOOLEAN NOT NULL DEFAULT FALSE
                            """
                        )
                        cur.execute(
                            f"""
                            ALTER TABLE {self.devices_table_name}
                            ADD COLUMN IF NOT EXISTS capture_interval_sec INTEGER NOT NULL DEFAULT 300
                            """
                        )
                        cur.execute(
                            f"""
                            ALTER TABLE {self.devices_table_name}
                            ADD COLUMN IF NOT EXISTS capture_updated_at TIMESTAMPTZ
                            """
                        )
                        cur.execute(
                            f"""
                            ALTER TABLE {self.devices_table_name}
                            ADD COLUMN IF NOT EXISTS capture_last_event_at TIMESTAMPTZ
                            """
                        )
                        cur.execute(
                            f"""
                            UPDATE {self.devices_table_name}
                            SET approved_at = COALESCE(approved_at, created_at)
                            WHERE status = '{self.active_device_status}'
                              AND approved_at IS NULL
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE INDEX IF NOT EXISTS idx_{self.devices_table_name}_user_id
                            ON {self.devices_table_name} (user_id)
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE TABLE IF NOT EXISTS {self.device_pairings_table_name} (
                                pairing_code TEXT PRIMARY KEY,
                                user_id TEXT NOT NULL REFERENCES {self.users_table_name} (user_id),
                                device_id TEXT NOT NULL,
                                status TEXT NOT NULL DEFAULT '{self.pairing_pending_status}',
                                approved_at TIMESTAMPTZ,
                                expires_at TIMESTAMPTZ NOT NULL,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            )
                            """
                        )
                        cur.execute(
                            f"""
                            ALTER TABLE {self.device_pairings_table_name}
                            ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT '{self.pairing_pending_status}'
                            """
                        )
                        cur.execute(
                            f"""
                            ALTER TABLE {self.device_pairings_table_name}
                            ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ
                            """
                        )
                        cur.execute(
                            f"""
                            ALTER TABLE {self.device_pairings_table_name}
                            ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ
                            """
                        )
                        cur.execute(
                            f"""
                            ALTER TABLE {self.device_pairings_table_name}
                            ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            """
                        )
                        cur.execute(
                            f"""
                            ALTER TABLE {self.device_pairings_table_name}
                            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            """
                        )
                        cur.execute(
                            f"""
                            UPDATE {self.device_pairings_table_name}
                            SET expires_at = COALESCE(expires_at, created_at + INTERVAL '10 minutes')
                            WHERE expires_at IS NULL
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE INDEX IF NOT EXISTS idx_{self.device_pairings_table_name}_user_id
                            ON {self.device_pairings_table_name} (user_id)
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE INDEX IF NOT EXISTS idx_{self.device_pairings_table_name}_status_expires
                            ON {self.device_pairings_table_name} (status, expires_at DESC)
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE TABLE IF NOT EXISTS {self.memory_query_logs_table_name} (
                                log_id BIGSERIAL PRIMARY KEY,
                                user_id TEXT NOT NULL REFERENCES {self.users_table_name} (user_id),
                                query_type TEXT NOT NULL,
                                query_text TEXT NOT NULL,
                                total_hits INTEGER NOT NULL DEFAULT 0,
                                answer_text TEXT,
                                answer_mode TEXT,
                                cited_memory_ids_json JSONB,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            )
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE INDEX IF NOT EXISTS idx_{self.memory_query_logs_table_name}_user_created
                            ON {self.memory_query_logs_table_name} (user_id, created_at DESC)
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE INDEX IF NOT EXISTS idx_{self.memory_query_logs_table_name}_type_created
                            ON {self.memory_query_logs_table_name} (query_type, created_at DESC)
                            """
                        )
                    conn.commit()
            except UserRegistryUnavailableError:
                raise
            except Exception as exc:
                raise UserRegistryUnavailableError(
                    f"Postgres schema initialization failed: {exc}"
                ) from exc

            self._schema_ready = True

    def _map_device_row(self, row: tuple[object, ...]) -> DeviceRecord:
        return DeviceRecord(
            device_id=str(row[0]),
            user_id=str(row[1]),
            status=_normalize_text(row[2]) or self.active_device_status,
            display_name=_normalize_text(row[3]) or None,
            registered_at=_normalize_timestamp(row[4]),
            approved_at=_normalize_timestamp(row[5]) if row[5] is not None else None,
            revoked_at=_normalize_timestamp(row[6]) if row[6] is not None else None,
            updated_at=_normalize_timestamp(row[7]) if row[7] is not None else None,
            capture_enabled=bool(row[8]),
            capture_interval_sec=int(row[9] or 300),
            capture_updated_at=(
                _normalize_timestamp(row[10]) if row[10] is not None else None
            ),
            capture_last_event_at=(
                _normalize_timestamp(row[11]) if row[11] is not None else None
            ),
        )

    def _map_pairing_row(self, row: tuple[object, ...]) -> DevicePairingRecord:
        return DevicePairingRecord(
            pairing_code=str(row[0]),
            user_id=str(row[1]),
            device_id=str(row[2]),
            status=_normalize_text(row[3]) or self.pairing_pending_status,
            created_at=_normalize_timestamp(row[4]),
            expires_at=_normalize_timestamp(row[5]),
            approved_at=_normalize_timestamp(row[6]) if row[6] is not None else None,
            updated_at=_normalize_timestamp(row[7]) if row[7] is not None else None,
        )

    def _map_memory_query_log_row(
        self, row: tuple[object, ...]
    ) -> MemoryQueryLogRecord:
        return MemoryQueryLogRecord(
            log_id=int(row[0]),
            user_id=str(row[1]),
            query_type=_normalize_text(row[2]),
            query_text=_normalize_text(row[3]),
            total_hits=int(row[4] or 0),
            answer_text=_normalize_text(row[5]) or None,
            answer_mode=_normalize_text(row[6]) or None,
            cited_memory_ids_json=_normalize_text(row[7]) or None,
            created_at=_normalize_timestamp(row[8]),
        )

    def create_user(self, user_id: str) -> UserRecord:
        normalized_user_id = _normalize_text(user_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")

        self._ensure_schema()
        query = f"""
            INSERT INTO {self.users_table_name} (user_id)
            VALUES (%s)
            ON CONFLICT (user_id) DO UPDATE
            SET user_id = EXCLUDED.user_id
            RETURNING user_id, created_at
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (normalized_user_id,))
                    row = cur.fetchone()
                conn.commit()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        if not row:
            raise UserRegistryUnavailableError("Postgres write failed: user row missing")
        return UserRecord(user_id=str(row[0]), created_at=_normalize_timestamp(row[1]))

    def get_user(self, user_id: str) -> UserRecord | None:
        normalized_user_id = _normalize_text(user_id)
        if not normalized_user_id:
            return None

        self._ensure_schema()
        query = f"""
            SELECT user_id, created_at
            FROM {self.users_table_name}
            WHERE user_id = %s
            LIMIT 1
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (normalized_user_id,))
                    row = cur.fetchone()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres read failed: {exc}"
            ) from exc

        if not row:
            return None
        return UserRecord(user_id=str(row[0]), created_at=_normalize_timestamp(row[1]))

    def register_device(self, *, user_id: str, device_id: str) -> DeviceRecord:
        normalized_user_id = _normalize_text(user_id)
        normalized_device_id = _normalize_text(device_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_device_id:
            raise ValueError("deviceId must not be blank")

        self._ensure_schema()
        user = self.get_user(normalized_user_id)
        if user is None:
            raise LookupError("userId is not registered")

        query = f"""
            INSERT INTO {self.devices_table_name} (
                device_id,
                user_id,
                status,
                display_name,
                approved_at,
                revoked_at,
                created_at,
                updated_at,
                capture_enabled,
                capture_interval_sec,
                capture_updated_at,
                capture_last_event_at
            ) VALUES (%s, %s, %s, %s, NOW(), NULL, NOW(), NOW(), %s, %s, %s, %s)
            ON CONFLICT (device_id) DO UPDATE
            SET updated_at = NOW()
            WHERE {self.devices_table_name}.user_id = EXCLUDED.user_id
            RETURNING
                device_id,
                user_id,
                status,
                display_name,
                created_at,
                approved_at,
                revoked_at,
                updated_at,
                capture_enabled,
                capture_interval_sec,
                capture_updated_at,
                capture_last_event_at
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            normalized_device_id,
                            normalized_user_id,
                            self.active_device_status,
                            normalized_device_id,
                            False,
                            300,
                            None,
                            None,
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        if not row:
            raise ValueError("deviceId is already registered to another user")
        return self._map_device_row(row)

    def get_device(self, device_id: str) -> DeviceRecord | None:
        normalized_device_id = _normalize_text(device_id)
        if not normalized_device_id:
            return None

        self._ensure_schema()
        query = f"""
            SELECT
                device_id,
                user_id,
                status,
                display_name,
                created_at,
                approved_at,
                revoked_at,
                updated_at,
                capture_enabled,
                capture_interval_sec,
                capture_updated_at,
                capture_last_event_at
            FROM {self.devices_table_name}
            WHERE device_id = %s
            LIMIT 1
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (normalized_device_id,))
                    row = cur.fetchone()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres read failed: {exc}"
            ) from exc

        if not row:
            return None
        return self._map_device_row(row)

    def list_devices(self, *, user_id: str) -> list[DeviceRecord]:
        normalized_user_id = _normalize_text(user_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")

        self._ensure_schema()
        query = f"""
            SELECT
                device_id,
                user_id,
                status,
                display_name,
                created_at,
                approved_at,
                revoked_at,
                updated_at,
                capture_enabled,
                capture_interval_sec,
                capture_updated_at,
                capture_last_event_at
            FROM {self.devices_table_name}
            WHERE user_id = %s
            ORDER BY updated_at DESC, created_at DESC, device_id ASC
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (normalized_user_id,))
                    rows = cur.fetchall()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres read failed: {exc}"
            ) from exc

        return [self._map_device_row(row) for row in rows]

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

        self._ensure_schema()
        query = f"""
            UPDATE {self.devices_table_name}
            SET
                display_name = %s,
                updated_at = NOW()
            WHERE user_id = %s
              AND device_id = %s
            RETURNING
                device_id,
                user_id,
                status,
                display_name,
                created_at,
                approved_at,
                revoked_at,
                updated_at,
                capture_enabled,
                capture_interval_sec,
                capture_updated_at,
                capture_last_event_at
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            normalized_display_name,
                            normalized_user_id,
                            normalized_device_id,
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        if not row:
            raise LookupError("deviceId is not registered")
        return self._map_device_row(row)

    def issue_pairing_code(
        self,
        *,
        user_id: str,
        device_id: str,
        pairing_code: str,
        expires_in_minutes: int,
    ) -> DevicePairingRecord:
        normalized_user_id = _normalize_text(user_id)
        normalized_device_id = _normalize_text(device_id)
        normalized_pairing_code = _normalize_text(pairing_code).upper()
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_device_id:
            raise ValueError("deviceId must not be blank")
        if not normalized_pairing_code:
            raise ValueError("pairingCode must not be blank")
        if expires_in_minutes < 1:
            raise ValueError("expiresInMinutes must be at least 1")

        user = self.get_user(normalized_user_id)
        if user is None:
            raise LookupError("userId is not registered")

        self._ensure_schema()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=expires_in_minutes)
        query = f"""
            INSERT INTO {self.device_pairings_table_name} (
                pairing_code,
                user_id,
                device_id,
                status,
                approved_at,
                expires_at,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, NULL, %s, NOW(), NOW())
            RETURNING
                pairing_code,
                user_id,
                device_id,
                status,
                created_at,
                expires_at,
                approved_at,
                updated_at
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            normalized_pairing_code,
                            normalized_user_id,
                            normalized_device_id,
                            self.pairing_pending_status,
                            expires_at,
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        if not row:
            raise UserRegistryUnavailableError("Postgres write failed: pairing row missing")
        return self._map_pairing_row(row)

    def get_pairing_code(self, pairing_code: str) -> DevicePairingRecord | None:
        normalized_pairing_code = _normalize_text(pairing_code).upper()
        if not normalized_pairing_code:
            return None

        self._ensure_schema()
        query = f"""
            SELECT
                pairing_code,
                user_id,
                device_id,
                status,
                created_at,
                expires_at,
                approved_at,
                updated_at
            FROM {self.device_pairings_table_name}
            WHERE pairing_code = %s
            LIMIT 1
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (normalized_pairing_code,))
                    row = cur.fetchone()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres read failed: {exc}"
            ) from exc

        if not row:
            return None
        return self._map_pairing_row(row)

    def list_pairing_codes(
        self,
        *,
        user_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[DevicePairingRecord]:
        normalized_user_id = _normalize_text(user_id)
        normalized_status = _normalize_text(status).lower()
        effective_limit = max(1, min(limit, 200))

        self._ensure_schema()
        conditions: list[str] = []
        params: list[object] = []
        if normalized_user_id:
            conditions.append("user_id = %s")
            params.append(normalized_user_id)
        if normalized_status:
            conditions.append("status = %s")
            params.append(normalized_status)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        query = f"""
            SELECT
                pairing_code,
                user_id,
                device_id,
                status,
                created_at,
                expires_at,
                approved_at,
                updated_at
            FROM {self.device_pairings_table_name}
            {where_clause}
            ORDER BY updated_at DESC, created_at DESC, pairing_code ASC
            LIMIT %s
        """
        params.append(effective_limit)
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, tuple(params))
                    rows = cur.fetchall()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres read failed: {exc}"
            ) from exc

        return [self._map_pairing_row(row) for row in rows]

    def update_pairing_status(
        self,
        *,
        pairing_code: str,
        status: str,
        approved: bool = False,
    ) -> DevicePairingRecord:
        normalized_pairing_code = _normalize_text(pairing_code).upper()
        normalized_status = _normalize_text(status).lower()
        if not normalized_pairing_code:
            raise ValueError("pairingCode must not be blank")
        if normalized_status not in {
            self.pairing_pending_status,
            self.pairing_approved_status,
            self.pairing_rejected_status,
        }:
            raise ValueError("pairing status is invalid")

        self._ensure_schema()
        approved_at_assignment = "NOW()" if approved else "approved_at"
        query = f"""
            UPDATE {self.device_pairings_table_name}
            SET
                status = %s,
                approved_at = {approved_at_assignment},
                updated_at = NOW()
            WHERE pairing_code = %s
            RETURNING
                pairing_code,
                user_id,
                device_id,
                status,
                created_at,
                expires_at,
                approved_at,
                updated_at
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            normalized_status,
                            normalized_pairing_code,
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        if not row:
            raise LookupError("pairingCode is not registered")
        return self._map_pairing_row(row)

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
        normalized_answer_text = _normalize_text(answer_text) or None
        normalized_answer_mode = _normalize_text(answer_mode) or None
        normalized_cited_memory_ids_json = _normalize_text(cited_memory_ids_json) or None
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if normalized_query_type not in {"search", "chat"}:
            raise ValueError("queryType must be one of: search, chat")
        if not normalized_query_text:
            raise ValueError("queryText must not be blank")

        self._ensure_schema()
        query = f"""
            INSERT INTO {self.memory_query_logs_table_name} (
                user_id,
                query_type,
                query_text,
                total_hits,
                answer_text,
                answer_mode,
                cited_memory_ids_json,
                created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
            RETURNING
                log_id,
                user_id,
                query_type,
                query_text,
                total_hits,
                answer_text,
                answer_mode,
                cited_memory_ids_json::text,
                created_at
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            normalized_user_id,
                            normalized_query_type,
                            normalized_query_text,
                            max(0, int(total_hits)),
                            normalized_answer_text,
                            normalized_answer_mode,
                            normalized_cited_memory_ids_json,
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        if not row:
            raise UserRegistryUnavailableError("Postgres write failed: memory query log row missing")
        return self._map_memory_query_log_row(row)

    def list_memory_query_logs(
        self,
        *,
        user_id: str | None = None,
        query_type: str | None = None,
        limit: int = 100,
    ) -> list[MemoryQueryLogRecord]:
        normalized_user_id = _normalize_text(user_id) or None
        normalized_query_type = _normalize_text(query_type).lower() or None
        effective_limit = max(1, min(int(limit), 500))

        self._ensure_schema()
        conditions: list[str] = []
        params: list[object] = []
        if normalized_user_id:
            conditions.append("user_id = %s")
            params.append(normalized_user_id)
        if normalized_query_type:
            conditions.append("query_type = %s")
            params.append(normalized_query_type)
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT
                log_id,
                user_id,
                query_type,
                query_text,
                total_hits,
                answer_text,
                answer_mode,
                cited_memory_ids_json::text,
                created_at
            FROM {self.memory_query_logs_table_name}
            {where_clause}
            ORDER BY created_at DESC, log_id DESC
            LIMIT %s
        """
        params.append(effective_limit)

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, tuple(params))
                    rows = cur.fetchall()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres read failed: {exc}"
            ) from exc

        return [self._map_memory_query_log_row(row) for row in rows]

    def approve_device(self, *, user_id: str, device_id: str) -> DeviceRecord:
        normalized_user_id = _normalize_text(user_id)
        normalized_device_id = _normalize_text(device_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_device_id:
            raise ValueError("deviceId must not be blank")

        existing_device = self.get_device(normalized_device_id)
        if existing_device is None:
            raise LookupError("deviceId is not registered")
        if existing_device.user_id != normalized_user_id:
            raise ValueError("deviceId is registered to another user")

        self._ensure_schema()
        query = f"""
            UPDATE {self.devices_table_name}
            SET
                status = %s,
                approved_at = NOW(),
                revoked_at = NULL,
                updated_at = NOW()
            WHERE user_id = %s
              AND device_id = %s
            RETURNING
                device_id,
                user_id,
                status,
                display_name,
                created_at,
                approved_at,
                revoked_at,
                updated_at,
                capture_enabled,
                capture_interval_sec,
                capture_updated_at,
                capture_last_event_at
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            self.active_device_status,
                            normalized_user_id,
                            normalized_device_id,
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        if not row:
            raise UserRegistryUnavailableError("Postgres write failed: device row missing")
        return self._map_device_row(row)

    def update_device_capture_control(
        self,
        *,
        user_id: str,
        device_id: str,
        enabled: bool,
        interval_sec: int,
    ) -> DeviceRecord:
        normalized_user_id = _normalize_text(user_id)
        normalized_device_id = _normalize_text(device_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_device_id:
            raise ValueError("deviceId must not be blank")

        self._ensure_schema()
        query = f"""
            UPDATE {self.devices_table_name}
            SET
                capture_enabled = %s,
                capture_interval_sec = %s,
                capture_updated_at = NOW()
            WHERE user_id = %s
              AND device_id = %s
            RETURNING
                device_id,
                user_id,
                status,
                display_name,
                created_at,
                approved_at,
                revoked_at,
                updated_at,
                capture_enabled,
                capture_interval_sec,
                capture_updated_at,
                capture_last_event_at
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            enabled,
                            interval_sec,
                            normalized_user_id,
                            normalized_device_id,
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        if not row:
            raise LookupError("deviceId is not registered")
        return self._map_device_row(row)

    def record_device_capture_event(
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

        self._ensure_schema()
        query = f"""
            UPDATE {self.devices_table_name}
            SET capture_last_event_at = NOW()
            WHERE user_id = %s
              AND device_id = %s
            RETURNING
                device_id,
                user_id,
                status,
                display_name,
                created_at,
                approved_at,
                revoked_at,
                updated_at,
                capture_enabled,
                capture_interval_sec,
                capture_updated_at,
                capture_last_event_at
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            normalized_user_id,
                            normalized_device_id,
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        if not row:
            raise LookupError("deviceId is not registered")
        return self._map_device_row(row)

    def revoke_device(self, *, user_id: str, device_id: str) -> DeviceRecord:
        normalized_user_id = _normalize_text(user_id)
        normalized_device_id = _normalize_text(device_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_device_id:
            raise ValueError("deviceId must not be blank")

        existing_device = self.get_device(normalized_device_id)
        if existing_device is None:
            raise LookupError("deviceId is not registered")
        if existing_device.user_id != normalized_user_id:
            raise ValueError("deviceId is registered to another user")

        self._ensure_schema()
        query = f"""
            UPDATE {self.devices_table_name}
            SET
                status = %s,
                revoked_at = NOW(),
                updated_at = NOW()
            WHERE user_id = %s
              AND device_id = %s
            RETURNING
                device_id,
                user_id,
                status,
                display_name,
                created_at,
                approved_at,
                revoked_at,
                updated_at,
                capture_enabled,
                capture_interval_sec,
                capture_updated_at,
                capture_last_event_at
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            self.revoked_device_status,
                            normalized_user_id,
                            normalized_device_id,
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        if not row:
            raise UserRegistryUnavailableError("Postgres write failed: device row missing")
        return self._map_device_row(row)

    def find_user_by_device_id(self, device_id: str) -> UserRecord | None:
        normalized_device_id = _normalize_text(device_id)
        if not normalized_device_id:
            return None

        self._ensure_schema()
        query = f"""
            SELECT u.user_id, u.created_at
            FROM {self.users_table_name} AS u
            INNER JOIN {self.devices_table_name} AS d
                ON d.user_id = u.user_id
            WHERE d.device_id = %s
            LIMIT 1
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (normalized_device_id,))
                    row = cur.fetchone()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres read failed: {exc}"
            ) from exc

        if not row:
            return None
        return UserRecord(user_id=str(row[0]), created_at=_normalize_timestamp(row[1]))

    def check_health(self) -> None:
        if not self._schema_ready:
            self._ensure_schema()
            return

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
        except UserRegistryUnavailableError:
            raise
        except Exception as exc:
            raise UserRegistryUnavailableError(
                f"Postgres health check failed: {exc}"
            ) from exc


def build_default_user_registry() -> PostgresUserRegistry:
    database_url = os.getenv("API_CAPTURE_DATABASE_URL", "").strip()
    if not database_url:
        raise ValueError("API_CAPTURE_DATABASE_URL is required for user/device storage")
    return PostgresUserRegistry(database_url)
