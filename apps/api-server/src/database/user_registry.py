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


class UserRegistryUnavailableError(RuntimeError):
    pass


class PostgresUserRegistry:
    users_table_name = "users"
    devices_table_name = "devices"

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
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            )
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

        existing_device = self.get_device(normalized_device_id)
        if (
            existing_device is not None
            and existing_device.user_id != normalized_user_id
        ):
            raise ValueError("deviceId is already registered to another user")

        query = f"""
            INSERT INTO {self.devices_table_name} (
                device_id,
                user_id,
                created_at,
                updated_at
            ) VALUES (%s, %s, NOW(), NOW())
            ON CONFLICT (device_id) DO UPDATE
            SET updated_at = NOW()
            RETURNING device_id, user_id, created_at
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (normalized_device_id, normalized_user_id),
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
        return DeviceRecord(
            device_id=str(row[0]),
            user_id=str(row[1]),
            registered_at=_normalize_timestamp(row[2]),
        )

    def get_device(self, device_id: str) -> DeviceRecord | None:
        normalized_device_id = _normalize_text(device_id)
        if not normalized_device_id:
            return None

        self._ensure_schema()
        query = f"""
            SELECT device_id, user_id, created_at
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
        return DeviceRecord(
            device_id=str(row[0]),
            user_id=str(row[1]),
            registered_at=_normalize_timestamp(row[2]),
        )

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
