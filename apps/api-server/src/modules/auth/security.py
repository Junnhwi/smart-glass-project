from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Any, Protocol


def _normalize_text(value: str | None) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    key: str
    max_attempts: int
    window_sec: int


DEFAULT_RATE_LIMIT_POLICIES = {
    "auth.signup.ip": RateLimitPolicy(
        key="auth.signup.ip",
        max_attempts=5,
        window_sec=600,
    ),
    "auth.signup.email": RateLimitPolicy(
        key="auth.signup.email",
        max_attempts=3,
        window_sec=600,
    ),
    "auth.login.ip": RateLimitPolicy(
        key="auth.login.ip",
        max_attempts=10,
        window_sec=300,
    ),
    "auth.login.email": RateLimitPolicy(
        key="auth.login.email",
        max_attempts=5,
        window_sec=300,
    ),
    "auth.refresh.ip": RateLimitPolicy(
        key="auth.refresh.ip",
        max_attempts=20,
        window_sec=300,
    ),
    "auth.oauth.google.start.ip": RateLimitPolicy(
        key="auth.oauth.google.start.ip",
        max_attempts=20,
        window_sec=300,
    ),
    "auth.oauth.google.exchange.ip": RateLimitPolicy(
        key="auth.oauth.google.exchange.ip",
        max_attempts=10,
        window_sec=300,
    ),
}


class AuthSecurityRepository(Protocol):
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
    ) -> Any: ...


class RateLimitExceededError(PermissionError):
    def __init__(
        self,
        *,
        policy_key: str,
        identifier: str,
        retry_after_sec: int,
    ) -> None:
        self.policy_key = policy_key
        self.identifier = identifier
        self.retry_after_sec = max(1, int(retry_after_sec))
        super().__init__(
            f"Too many requests for {policy_key}. Retry after {self.retry_after_sec} seconds."
        )


class AuthSecurityService:
    def __init__(
        self,
        repository: AuthSecurityRepository | None = None,
        *,
        policies: dict[str, RateLimitPolicy] | None = None,
    ) -> None:
        self.repository = repository
        self.policies = dict(DEFAULT_RATE_LIMIT_POLICIES)
        if policies:
            self.policies.update(policies)
        self._attempts: dict[tuple[str, str], deque[float]] = {}
        self._lock = Lock()

    def enforce_rate_limit(self, *, policy_key: str, identifier: str | None) -> None:
        policy = self.policies.get(policy_key)
        if policy is None:
            raise ValueError(f"Unknown auth rate-limit policy: {policy_key}")

        normalized_identifier = _normalize_text(identifier) or "anonymous"
        now = monotonic()
        window_start = now - float(policy.window_sec)
        bucket_key = (policy.key, normalized_identifier)

        with self._lock:
            attempts = self._attempts.get(bucket_key)
            if attempts is None:
                attempts = deque()
                self._attempts[bucket_key] = attempts

            while attempts and attempts[0] <= window_start:
                attempts.popleft()

            if len(attempts) >= policy.max_attempts:
                retry_after_sec = int(max(1, policy.window_sec - (now - attempts[0])))
                raise RateLimitExceededError(
                    policy_key=policy.key,
                    identifier=normalized_identifier,
                    retry_after_sec=retry_after_sec,
                )

            attempts.append(now)

    def record_event(
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
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.repository is None:
            return

        normalized_metadata_json = None
        if metadata:
            normalized_metadata_json = json.dumps(
                metadata,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )

        self.repository.record_auth_event(
            event_type=event_type,
            outcome=outcome,
            user_id=user_id,
            email=email,
            provider=provider,
            device_id=device_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata_json=normalized_metadata_json,
        )


def build_default_auth_security_service(
    repository: AuthSecurityRepository | None,
) -> AuthSecurityService:
    return AuthSecurityService(repository=repository)
