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


def _normalize_email(value: Any) -> str:
    return _normalize_text(value).lower()


def _normalize_timestamp(value: Any) -> str | None:
    normalized = _normalize_text(value)
    if not normalized:
        return None

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
class AuthUserRecord:
    user_id: str
    email: str
    password_hash: str
    display_name: str | None
    role: str
    status: str
    created_at: str
    last_login_at: str | None


@dataclass(frozen=True, slots=True)
class AuthSessionRecord:
    session_id: str
    user_id: str
    refresh_token_hash: str
    device_id: str | None
    user_agent: str | None
    ip_address: str | None
    created_at: str
    expires_at: str
    revoked_at: str | None
    replaced_by_session_id: str | None


class AuthStoreUnavailableError(RuntimeError):
    pass


class PostgresAuthStore:
    users_table_name = "users"
    auth_users_table_name = "auth_users"
    auth_sessions_table_name = "auth_sessions"
    auth_revocations_table_name = "auth_revoked_access_tokens"

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url.strip()
        if not self.database_url:
            raise ValueError("database_url must not be blank")
        self._lock = Lock()
        self._schema_ready = False

    def _require_driver(self) -> None:
        if psycopg is None:
            raise RuntimeError(
                "psycopg is required for api-server auth storage. "
                "Install apps/api-server requirements."
            )

    def _connect(self):  # type: ignore[no-untyped-def]
        self._require_driver()
        try:
            return psycopg.connect(self.database_url)
        except Exception as exc:
            raise AuthStoreUnavailableError(
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
                            CREATE TABLE IF NOT EXISTS {self.auth_users_table_name} (
                                user_id TEXT PRIMARY KEY REFERENCES {self.users_table_name} (user_id) ON DELETE CASCADE,
                                email TEXT NOT NULL UNIQUE,
                                password_hash TEXT NOT NULL,
                                display_name TEXT,
                                role TEXT NOT NULL DEFAULT 'user',
                                status TEXT NOT NULL DEFAULT 'active',
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                last_login_at TIMESTAMPTZ
                            )
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE TABLE IF NOT EXISTS {self.auth_sessions_table_name} (
                                session_id TEXT PRIMARY KEY,
                                user_id TEXT NOT NULL REFERENCES {self.auth_users_table_name} (user_id) ON DELETE CASCADE,
                                refresh_token_hash TEXT NOT NULL UNIQUE,
                                device_id TEXT,
                                user_agent TEXT,
                                ip_address TEXT,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                expires_at TIMESTAMPTZ NOT NULL,
                                revoked_at TIMESTAMPTZ,
                                replaced_by_session_id TEXT
                            )
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE INDEX IF NOT EXISTS idx_{self.auth_sessions_table_name}_user_id
                            ON {self.auth_sessions_table_name} (user_id)
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE TABLE IF NOT EXISTS {self.auth_revocations_table_name} (
                                jti TEXT PRIMARY KEY,
                                user_id TEXT NOT NULL REFERENCES {self.auth_users_table_name} (user_id) ON DELETE CASCADE,
                                expires_at TIMESTAMPTZ NOT NULL,
                                revoked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            )
                            """
                        )
                    conn.commit()
            except AuthStoreUnavailableError:
                raise
            except Exception as exc:
                raise AuthStoreUnavailableError(
                    f"Postgres schema initialization failed: {exc}"
                ) from exc

            self._schema_ready = True

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
        normalized_user_id = _normalize_text(user_id)
        normalized_email = _normalize_email(email)
        normalized_password_hash = _normalize_text(password_hash)
        normalized_display_name = _normalize_text(display_name) or None
        normalized_role = _normalize_text(role) or "user"
        normalized_status = _normalize_text(status) or "active"

        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_email:
            raise ValueError("email must not be blank")
        if not normalized_password_hash:
            raise ValueError("passwordHash must not be blank")

        self._ensure_schema()

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        INSERT INTO {self.users_table_name} (user_id)
                        VALUES (%s)
                        ON CONFLICT (user_id) DO NOTHING
                        """,
                        (normalized_user_id,),
                    )
                    cur.execute(
                        f"""
                        INSERT INTO {self.auth_users_table_name} (
                            user_id,
                            email,
                            password_hash,
                            display_name,
                            role,
                            status,
                            created_at,
                            updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW())
                        ON CONFLICT (user_id) DO NOTHING
                        RETURNING
                            user_id,
                            email,
                            password_hash,
                            display_name,
                            role,
                            status,
                            created_at,
                            last_login_at
                        """,
                        (
                            normalized_user_id,
                            normalized_email,
                            normalized_password_hash,
                            normalized_display_name,
                            normalized_role,
                            normalized_status,
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except AuthStoreUnavailableError:
            raise
        except Exception as exc:
            raise AuthStoreUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        if row:
            return AuthUserRecord(
                user_id=str(row[0]),
                email=str(row[1]),
                password_hash=str(row[2]),
                display_name=_normalize_text(row[3]) or None,
                role=str(row[4]),
                status=str(row[5]),
                created_at=_normalize_timestamp(row[6]) or "",
                last_login_at=_normalize_timestamp(row[7]),
            )

        existing_by_email = self.get_auth_user_by_email(normalized_email)
        if existing_by_email is not None and existing_by_email.user_id != normalized_user_id:
            raise ValueError("email is already registered")

        existing_by_user = self.get_auth_user_by_user_id(normalized_user_id)
        if existing_by_user is not None:
            raise ValueError("userId is already registered for sign-in")

        raise AuthStoreUnavailableError("Postgres write failed: auth user row missing")

    def get_auth_user_by_email(self, email: str) -> AuthUserRecord | None:
        normalized_email = _normalize_email(email)
        if not normalized_email:
            return None

        self._ensure_schema()
        query = f"""
            SELECT
                user_id,
                email,
                password_hash,
                display_name,
                role,
                status,
                created_at,
                last_login_at
            FROM {self.auth_users_table_name}
            WHERE email = %s
            LIMIT 1
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (normalized_email,))
                    row = cur.fetchone()
        except AuthStoreUnavailableError:
            raise
        except Exception as exc:
            raise AuthStoreUnavailableError(
                f"Postgres read failed: {exc}"
            ) from exc

        if not row:
            return None
        return AuthUserRecord(
            user_id=str(row[0]),
            email=str(row[1]),
            password_hash=str(row[2]),
            display_name=_normalize_text(row[3]) or None,
            role=str(row[4]),
            status=str(row[5]),
            created_at=_normalize_timestamp(row[6]) or "",
            last_login_at=_normalize_timestamp(row[7]),
        )

    def get_auth_user_by_user_id(self, user_id: str) -> AuthUserRecord | None:
        normalized_user_id = _normalize_text(user_id)
        if not normalized_user_id:
            return None

        self._ensure_schema()
        query = f"""
            SELECT
                user_id,
                email,
                password_hash,
                display_name,
                role,
                status,
                created_at,
                last_login_at
            FROM {self.auth_users_table_name}
            WHERE user_id = %s
            LIMIT 1
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (normalized_user_id,))
                    row = cur.fetchone()
        except AuthStoreUnavailableError:
            raise
        except Exception as exc:
            raise AuthStoreUnavailableError(
                f"Postgres read failed: {exc}"
            ) from exc

        if not row:
            return None
        return AuthUserRecord(
            user_id=str(row[0]),
            email=str(row[1]),
            password_hash=str(row[2]),
            display_name=_normalize_text(row[3]) or None,
            role=str(row[4]),
            status=str(row[5]),
            created_at=_normalize_timestamp(row[6]) or "",
            last_login_at=_normalize_timestamp(row[7]),
        )

    def touch_last_login(self, user_id: str) -> AuthUserRecord:
        normalized_user_id = _normalize_text(user_id)
        if not normalized_user_id:
            raise ValueError("userId must not be blank")

        self._ensure_schema()
        query = f"""
            UPDATE {self.auth_users_table_name}
            SET last_login_at = NOW(), updated_at = NOW()
            WHERE user_id = %s
            RETURNING
                user_id,
                email,
                password_hash,
                display_name,
                role,
                status,
                created_at,
                last_login_at
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (normalized_user_id,))
                    row = cur.fetchone()
                conn.commit()
        except AuthStoreUnavailableError:
            raise
        except Exception as exc:
            raise AuthStoreUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        if not row:
            raise LookupError("auth user is not registered")
        return AuthUserRecord(
            user_id=str(row[0]),
            email=str(row[1]),
            password_hash=str(row[2]),
            display_name=_normalize_text(row[3]) or None,
            role=str(row[4]),
            status=str(row[5]),
            created_at=_normalize_timestamp(row[6]) or "",
            last_login_at=_normalize_timestamp(row[7]),
        )

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
        normalized_session_id = _normalize_text(session_id)
        normalized_user_id = _normalize_text(user_id)
        normalized_refresh_token_hash = _normalize_text(refresh_token_hash)
        normalized_expires_at = _normalize_timestamp(expires_at)
        normalized_device_id = _normalize_text(device_id) or None
        normalized_user_agent = _normalize_text(user_agent) or None
        normalized_ip_address = _normalize_text(ip_address) or None

        if not normalized_session_id:
            raise ValueError("sessionId must not be blank")
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_refresh_token_hash:
            raise ValueError("refreshTokenHash must not be blank")
        if not normalized_expires_at:
            raise ValueError("expiresAt must not be blank")

        self._ensure_schema()
        query = f"""
            INSERT INTO {self.auth_sessions_table_name} (
                session_id,
                user_id,
                refresh_token_hash,
                device_id,
                user_agent,
                ip_address,
                created_at,
                expires_at
            ) VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s::timestamptz)
            RETURNING
                session_id,
                user_id,
                refresh_token_hash,
                device_id,
                user_agent,
                ip_address,
                created_at,
                expires_at,
                revoked_at,
                replaced_by_session_id
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            normalized_session_id,
                            normalized_user_id,
                            normalized_refresh_token_hash,
                            normalized_device_id,
                            normalized_user_agent,
                            normalized_ip_address,
                            normalized_expires_at,
                        ),
                    )
                    row = cur.fetchone()
                conn.commit()
        except AuthStoreUnavailableError:
            raise
        except Exception as exc:
            raise AuthStoreUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        if not row:
            raise AuthStoreUnavailableError("Postgres write failed: session row missing")
        return AuthSessionRecord(
            session_id=str(row[0]),
            user_id=str(row[1]),
            refresh_token_hash=str(row[2]),
            device_id=_normalize_text(row[3]) or None,
            user_agent=_normalize_text(row[4]) or None,
            ip_address=_normalize_text(row[5]) or None,
            created_at=_normalize_timestamp(row[6]) or "",
            expires_at=_normalize_timestamp(row[7]) or "",
            revoked_at=_normalize_timestamp(row[8]),
            replaced_by_session_id=_normalize_text(row[9]) or None,
        )

    def get_refresh_session_by_token_hash(
        self,
        refresh_token_hash: str,
    ) -> AuthSessionRecord | None:
        normalized_refresh_token_hash = _normalize_text(refresh_token_hash)
        if not normalized_refresh_token_hash:
            return None

        self._ensure_schema()
        query = f"""
            SELECT
                session_id,
                user_id,
                refresh_token_hash,
                device_id,
                user_agent,
                ip_address,
                created_at,
                expires_at,
                revoked_at,
                replaced_by_session_id
            FROM {self.auth_sessions_table_name}
            WHERE refresh_token_hash = %s
            LIMIT 1
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (normalized_refresh_token_hash,))
                    row = cur.fetchone()
        except AuthStoreUnavailableError:
            raise
        except Exception as exc:
            raise AuthStoreUnavailableError(
                f"Postgres read failed: {exc}"
            ) from exc

        if not row:
            return None
        return AuthSessionRecord(
            session_id=str(row[0]),
            user_id=str(row[1]),
            refresh_token_hash=str(row[2]),
            device_id=_normalize_text(row[3]) or None,
            user_agent=_normalize_text(row[4]) or None,
            ip_address=_normalize_text(row[5]) or None,
            created_at=_normalize_timestamp(row[6]) or "",
            expires_at=_normalize_timestamp(row[7]) or "",
            revoked_at=_normalize_timestamp(row[8]),
            replaced_by_session_id=_normalize_text(row[9]) or None,
        )

    def revoke_refresh_session(
        self,
        *,
        session_id: str,
        replaced_by_session_id: str | None = None,
    ) -> bool:
        normalized_session_id = _normalize_text(session_id)
        normalized_replaced_by = _normalize_text(replaced_by_session_id) or None
        if not normalized_session_id:
            return False

        self._ensure_schema()
        query = f"""
            UPDATE {self.auth_sessions_table_name}
            SET
                revoked_at = COALESCE(revoked_at, NOW()),
                replaced_by_session_id = COALESCE(%s, replaced_by_session_id)
            WHERE session_id = %s
            RETURNING session_id
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (normalized_replaced_by, normalized_session_id))
                    row = cur.fetchone()
                conn.commit()
        except AuthStoreUnavailableError:
            raise
        except Exception as exc:
            raise AuthStoreUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        return row is not None

    def revoke_access_token(
        self,
        *,
        jti: str,
        user_id: str,
        expires_at: str,
    ) -> bool:
        normalized_jti = _normalize_text(jti)
        normalized_user_id = _normalize_text(user_id)
        normalized_expires_at = _normalize_timestamp(expires_at)
        if not normalized_jti or not normalized_user_id or not normalized_expires_at:
            return False

        self._ensure_schema()
        query = f"""
            INSERT INTO {self.auth_revocations_table_name} (
                jti,
                user_id,
                expires_at,
                revoked_at
            ) VALUES (%s, %s, %s::timestamptz, NOW())
            ON CONFLICT (jti) DO NOTHING
            RETURNING jti
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (normalized_jti, normalized_user_id, normalized_expires_at),
                    )
                    row = cur.fetchone()
                conn.commit()
        except AuthStoreUnavailableError:
            raise
        except Exception as exc:
            raise AuthStoreUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        return row is not None

    def is_access_token_revoked(self, jti: str) -> bool:
        normalized_jti = _normalize_text(jti)
        if not normalized_jti:
            return False

        self._ensure_schema()
        query = f"""
            SELECT 1
            FROM {self.auth_revocations_table_name}
            WHERE jti = %s
              AND expires_at > NOW()
            LIMIT 1
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (normalized_jti,))
                    row = cur.fetchone()
        except AuthStoreUnavailableError:
            raise
        except Exception as exc:
            raise AuthStoreUnavailableError(
                f"Postgres read failed: {exc}"
            ) from exc

        return row is not None

    def check_health(self) -> None:
        if not self._schema_ready:
            self._ensure_schema()
            return

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    cur.fetchone()
        except AuthStoreUnavailableError:
            raise
        except Exception as exc:
            raise AuthStoreUnavailableError(
                f"Postgres health check failed: {exc}"
            ) from exc


def build_default_auth_store() -> PostgresAuthStore:
    database_url = os.getenv("API_CAPTURE_DATABASE_URL", "").strip()
    if not database_url:
        raise ValueError("API_CAPTURE_DATABASE_URL is required for auth storage")
    return PostgresAuthStore(database_url)
