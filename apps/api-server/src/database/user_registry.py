from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
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
    approved_at: str | None = None
    revoked_at: str | None = None
    updated_at: str | None = None


class UserRegistryUnavailableError(RuntimeError):
    pass


class PostgresUserRegistry:
    users_table_name = "users"
    devices_table_name = "devices"
    active_device_status = "active"
    revoked_device_status = "revoked"

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
                                approved_at TIMESTAMPTZ,
                                revoked_at TIMESTAMPTZ,
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
            registered_at=_normalize_timestamp(row[3]),
            approved_at=_normalize_timestamp(row[4]) if row[4] is not None else None,
            revoked_at=_normalize_timestamp(row[5]) if row[5] is not None else None,
            updated_at=_normalize_timestamp(row[6]) if row[6] is not None else None,
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
                approved_at,
                revoked_at,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, NOW(), NULL, NOW(), NOW())
            ON CONFLICT (device_id) DO UPDATE
            SET updated_at = NOW()
            WHERE {self.devices_table_name}.user_id = EXCLUDED.user_id
            RETURNING
                device_id,
                user_id,
                status,
                created_at,
                approved_at,
                revoked_at,
                updated_at
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
                created_at,
                approved_at,
                revoked_at,
                updated_at
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
                created_at,
                approved_at,
                revoked_at,
                updated_at
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
                created_at,
                approved_at,
                revoked_at,
                updated_at
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
                created_at,
                approved_at,
                revoked_at,
                updated_at
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
