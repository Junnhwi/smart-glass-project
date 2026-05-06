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


@dataclass(frozen=True, slots=True)
class AuthIdentityRecord:
    provider: str
    provider_user_id: str
    user_id: str
    email: str | None
    email_verified: bool
    display_name: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AuthOauthStateRecord:
    state: str
    provider: str
    redirect_uri: str
    code_verifier: str
    expires_at: str
    consumed_at: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class AuthOauthHandoffRecord:
    handoff_code: str
    provider: str
    user_id: str
    expires_at: str
    consumed_at: str | None
    created_at: str


@dataclass(frozen=True, slots=True)
class AuthAuditEventRecord:
    event_type: str
    outcome: str
    user_id: str | None
    email: str | None
    provider: str | None
    device_id: str | None
    ip_address: str | None
    user_agent: str | None
    metadata_json: str | None
    created_at: str


class AuthStoreUnavailableError(RuntimeError):
    pass


class PostgresAuthStore:
    users_table_name = "users"
    auth_users_table_name = "auth_users"
    auth_sessions_table_name = "auth_sessions"
    auth_revocations_table_name = "auth_revoked_access_tokens"
    auth_identities_table_name = "auth_identities"
    auth_oauth_states_table_name = "auth_oauth_states"
    auth_oauth_handoffs_table_name = "auth_oauth_handoffs"
    auth_audit_logs_table_name = "auth_audit_logs"

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
                        cur.execute(
                            f"""
                            CREATE TABLE IF NOT EXISTS {self.auth_identities_table_name} (
                                provider TEXT NOT NULL,
                                provider_user_id TEXT NOT NULL,
                                user_id TEXT NOT NULL REFERENCES {self.auth_users_table_name} (user_id) ON DELETE CASCADE,
                                email TEXT,
                                email_verified BOOLEAN NOT NULL DEFAULT FALSE,
                                display_name TEXT,
                                profile_json JSONB,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                PRIMARY KEY (provider, provider_user_id)
                            )
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE INDEX IF NOT EXISTS idx_{self.auth_identities_table_name}_user_id
                            ON {self.auth_identities_table_name} (user_id)
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE TABLE IF NOT EXISTS {self.auth_oauth_states_table_name} (
                                state TEXT PRIMARY KEY,
                                provider TEXT NOT NULL,
                                redirect_uri TEXT NOT NULL,
                                code_verifier TEXT NOT NULL,
                                expires_at TIMESTAMPTZ NOT NULL,
                                consumed_at TIMESTAMPTZ,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            )
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE TABLE IF NOT EXISTS {self.auth_oauth_handoffs_table_name} (
                                handoff_code TEXT PRIMARY KEY,
                                provider TEXT NOT NULL,
                                user_id TEXT NOT NULL REFERENCES {self.auth_users_table_name} (user_id) ON DELETE CASCADE,
                                expires_at TIMESTAMPTZ NOT NULL,
                                consumed_at TIMESTAMPTZ,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            )
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE TABLE IF NOT EXISTS {self.auth_audit_logs_table_name} (
                                event_id BIGSERIAL PRIMARY KEY,
                                event_type TEXT NOT NULL,
                                outcome TEXT NOT NULL,
                                user_id TEXT,
                                email TEXT,
                                provider TEXT,
                                device_id TEXT,
                                ip_address TEXT,
                                user_agent TEXT,
                                metadata_json JSONB,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                            )
                            """
                        )
                        cur.execute(
                            f"""
                            CREATE INDEX IF NOT EXISTS idx_{self.auth_audit_logs_table_name}_event_created_at
                            ON {self.auth_audit_logs_table_name} (event_type, created_at DESC)
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

    def get_auth_identity(
        self,
        *,
        provider: str,
        provider_user_id: str,
    ) -> AuthIdentityRecord | None:
        normalized_provider = _normalize_text(provider)
        normalized_provider_user_id = _normalize_text(provider_user_id)
        if not normalized_provider or not normalized_provider_user_id:
            return None

        self._ensure_schema()
        query = f"""
            SELECT
                provider,
                provider_user_id,
                user_id,
                email,
                email_verified,
                display_name,
                created_at,
                updated_at
            FROM {self.auth_identities_table_name}
            WHERE provider = %s
              AND provider_user_id = %s
            LIMIT 1
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (normalized_provider, normalized_provider_user_id),
                    )
                    row = cur.fetchone()
        except AuthStoreUnavailableError:
            raise
        except Exception as exc:
            raise AuthStoreUnavailableError(
                f"Postgres read failed: {exc}"
            ) from exc

        if not row:
            return None
        return AuthIdentityRecord(
            provider=str(row[0]),
            provider_user_id=str(row[1]),
            user_id=str(row[2]),
            email=_normalize_email(row[3]) or None,
            email_verified=bool(row[4]),
            display_name=_normalize_text(row[5]) or None,
            created_at=_normalize_timestamp(row[6]) or "",
            updated_at=_normalize_timestamp(row[7]) or "",
        )

    def upsert_auth_identity(
        self,
        *,
        provider: str,
        provider_user_id: str,
        user_id: str,
        email: str | None,
        email_verified: bool,
        display_name: str | None,
        profile_json: str | None,
    ) -> AuthIdentityRecord:
        normalized_provider = _normalize_text(provider)
        normalized_provider_user_id = _normalize_text(provider_user_id)
        normalized_user_id = _normalize_text(user_id)
        normalized_email = _normalize_email(email) or None
        normalized_display_name = _normalize_text(display_name) or None
        normalized_profile_json = _normalize_text(profile_json) or None

        if not normalized_provider:
            raise ValueError("provider must not be blank")
        if not normalized_provider_user_id:
            raise ValueError("providerUserId must not be blank")
        if not normalized_user_id:
            raise ValueError("userId must not be blank")

        self._ensure_schema()
        query = f"""
            INSERT INTO {self.auth_identities_table_name} (
                provider,
                provider_user_id,
                user_id,
                email,
                email_verified,
                display_name,
                profile_json,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, NOW(), NOW())
            ON CONFLICT (provider, provider_user_id) DO UPDATE SET
                user_id = EXCLUDED.user_id,
                email = EXCLUDED.email,
                email_verified = EXCLUDED.email_verified,
                display_name = EXCLUDED.display_name,
                profile_json = EXCLUDED.profile_json,
                updated_at = NOW()
            RETURNING
                provider,
                provider_user_id,
                user_id,
                email,
                email_verified,
                display_name,
                created_at,
                updated_at
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            normalized_provider,
                            normalized_provider_user_id,
                            normalized_user_id,
                            normalized_email,
                            bool(email_verified),
                            normalized_display_name,
                            normalized_profile_json,
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
            raise AuthStoreUnavailableError("Postgres write failed: auth identity row missing")
        return AuthIdentityRecord(
            provider=str(row[0]),
            provider_user_id=str(row[1]),
            user_id=str(row[2]),
            email=_normalize_email(row[3]) or None,
            email_verified=bool(row[4]),
            display_name=_normalize_text(row[5]) or None,
            created_at=_normalize_timestamp(row[6]) or "",
            updated_at=_normalize_timestamp(row[7]) or "",
        )

    def create_oauth_state(
        self,
        *,
        state: str,
        provider: str,
        redirect_uri: str,
        code_verifier: str,
        expires_at: str,
    ) -> AuthOauthStateRecord:
        normalized_state = _normalize_text(state)
        normalized_provider = _normalize_text(provider)
        normalized_redirect_uri = _normalize_text(redirect_uri)
        normalized_code_verifier = _normalize_text(code_verifier)
        normalized_expires_at = _normalize_timestamp(expires_at)

        if not normalized_state:
            raise ValueError("state must not be blank")
        if not normalized_provider:
            raise ValueError("provider must not be blank")
        if not normalized_redirect_uri:
            raise ValueError("redirectUri must not be blank")
        if not normalized_code_verifier:
            raise ValueError("codeVerifier must not be blank")
        if not normalized_expires_at:
            raise ValueError("expiresAt must not be blank")

        self._ensure_schema()
        query = f"""
            INSERT INTO {self.auth_oauth_states_table_name} (
                state,
                provider,
                redirect_uri,
                code_verifier,
                expires_at,
                created_at
            ) VALUES (%s, %s, %s, %s, %s::timestamptz, NOW())
            ON CONFLICT (state) DO UPDATE SET
                provider = EXCLUDED.provider,
                redirect_uri = EXCLUDED.redirect_uri,
                code_verifier = EXCLUDED.code_verifier,
                expires_at = EXCLUDED.expires_at,
                consumed_at = NULL,
                created_at = NOW()
            RETURNING
                state,
                provider,
                redirect_uri,
                code_verifier,
                expires_at,
                consumed_at,
                created_at
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            normalized_state,
                            normalized_provider,
                            normalized_redirect_uri,
                            normalized_code_verifier,
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
            raise AuthStoreUnavailableError("Postgres write failed: oauth state row missing")
        return AuthOauthStateRecord(
            state=str(row[0]),
            provider=str(row[1]),
            redirect_uri=str(row[2]),
            code_verifier=str(row[3]),
            expires_at=_normalize_timestamp(row[4]) or "",
            consumed_at=_normalize_timestamp(row[5]),
            created_at=_normalize_timestamp(row[6]) or "",
        )

    def consume_oauth_state(self, state: str) -> AuthOauthStateRecord | None:
        normalized_state = _normalize_text(state)
        if not normalized_state:
            return None

        self._ensure_schema()
        query = f"""
            UPDATE {self.auth_oauth_states_table_name}
            SET consumed_at = COALESCE(consumed_at, NOW())
            WHERE state = %s
              AND consumed_at IS NULL
            RETURNING
                state,
                provider,
                redirect_uri,
                code_verifier,
                expires_at,
                consumed_at,
                created_at
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (normalized_state,))
                    row = cur.fetchone()
                conn.commit()
        except AuthStoreUnavailableError:
            raise
        except Exception as exc:
            raise AuthStoreUnavailableError(
                f"Postgres write failed: {exc}"
            ) from exc

        if not row:
            return None
        return AuthOauthStateRecord(
            state=str(row[0]),
            provider=str(row[1]),
            redirect_uri=str(row[2]),
            code_verifier=str(row[3]),
            expires_at=_normalize_timestamp(row[4]) or "",
            consumed_at=_normalize_timestamp(row[5]),
            created_at=_normalize_timestamp(row[6]) or "",
        )

    def create_oauth_handoff(
        self,
        *,
        handoff_code: str,
        provider: str,
        user_id: str,
        expires_at: str,
    ) -> AuthOauthHandoffRecord:
        normalized_handoff_code = _normalize_text(handoff_code)
        normalized_provider = _normalize_text(provider)
        normalized_user_id = _normalize_text(user_id)
        normalized_expires_at = _normalize_timestamp(expires_at)

        if not normalized_handoff_code:
            raise ValueError("handoffCode must not be blank")
        if not normalized_provider:
            raise ValueError("provider must not be blank")
        if not normalized_user_id:
            raise ValueError("userId must not be blank")
        if not normalized_expires_at:
            raise ValueError("expiresAt must not be blank")

        self._ensure_schema()
        query = f"""
            INSERT INTO {self.auth_oauth_handoffs_table_name} (
                handoff_code,
                provider,
                user_id,
                expires_at,
                created_at
            ) VALUES (%s, %s, %s, %s::timestamptz, NOW())
            RETURNING
                handoff_code,
                provider,
                user_id,
                expires_at,
                consumed_at,
                created_at
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            normalized_handoff_code,
                            normalized_provider,
                            normalized_user_id,
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
            raise AuthStoreUnavailableError("Postgres write failed: oauth handoff row missing")
        return AuthOauthHandoffRecord(
            handoff_code=str(row[0]),
            provider=str(row[1]),
            user_id=str(row[2]),
            expires_at=_normalize_timestamp(row[3]) or "",
            consumed_at=_normalize_timestamp(row[4]),
            created_at=_normalize_timestamp(row[5]) or "",
        )

    def consume_oauth_handoff(
        self,
        *,
        handoff_code: str,
        provider: str,
    ) -> AuthOauthHandoffRecord | None:
        normalized_handoff_code = _normalize_text(handoff_code)
        normalized_provider = _normalize_text(provider)
        if not normalized_handoff_code or not normalized_provider:
            return None

        self._ensure_schema()
        query = f"""
            UPDATE {self.auth_oauth_handoffs_table_name}
            SET consumed_at = COALESCE(consumed_at, NOW())
            WHERE handoff_code = %s
              AND provider = %s
              AND consumed_at IS NULL
            RETURNING
                handoff_code,
                provider,
                user_id,
                expires_at,
                consumed_at,
                created_at
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (normalized_handoff_code, normalized_provider),
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
            return None
        return AuthOauthHandoffRecord(
            handoff_code=str(row[0]),
            provider=str(row[1]),
            user_id=str(row[2]),
            expires_at=_normalize_timestamp(row[3]) or "",
            consumed_at=_normalize_timestamp(row[4]),
            created_at=_normalize_timestamp(row[5]) or "",
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

    def record_auth_event(
        self,
        *,
        event_type: str,
        outcome: str,
        user_id: str | None = None,
        email: str | None = None,
        provider: str | None = None,
        device_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata_json: str | None = None,
    ) -> AuthAuditEventRecord:
        normalized_event_type = _normalize_text(event_type)
        normalized_outcome = _normalize_text(outcome)
        normalized_user_id = _normalize_text(user_id) or None
        normalized_email = _normalize_email(email) or None
        normalized_provider = _normalize_text(provider) or None
        normalized_device_id = _normalize_text(device_id) or None
        normalized_ip_address = _normalize_text(ip_address) or None
        normalized_user_agent = _normalize_text(user_agent) or None
        normalized_metadata_json = _normalize_text(metadata_json) or None

        if not normalized_event_type:
            raise ValueError("eventType must not be blank")
        if not normalized_outcome:
            raise ValueError("outcome must not be blank")

        self._ensure_schema()
        query = f"""
            INSERT INTO {self.auth_audit_logs_table_name} (
                event_type,
                outcome,
                user_id,
                email,
                provider,
                device_id,
                ip_address,
                user_agent,
                metadata_json,
                created_at
            ) VALUES (
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s,
                %s::jsonb,
                NOW()
            )
            RETURNING
                event_type,
                outcome,
                user_id,
                email,
                provider,
                device_id,
                ip_address,
                user_agent,
                metadata_json::text,
                created_at
        """

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        query,
                        (
                            normalized_event_type,
                            normalized_outcome,
                            normalized_user_id,
                            normalized_email,
                            normalized_provider,
                            normalized_device_id,
                            normalized_ip_address,
                            normalized_user_agent,
                            normalized_metadata_json,
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
            raise AuthStoreUnavailableError("Postgres write failed: auth audit row missing")
        return AuthAuditEventRecord(
            event_type=str(row[0]),
            outcome=str(row[1]),
            user_id=_normalize_text(row[2]) or None,
            email=_normalize_email(row[3]) or None,
            provider=_normalize_text(row[4]) or None,
            device_id=_normalize_text(row[5]) or None,
            ip_address=_normalize_text(row[6]) or None,
            user_agent=_normalize_text(row[7]) or None,
            metadata_json=_normalize_text(row[8]) or None,
            created_at=_normalize_timestamp(row[9]) or "",
        )

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
