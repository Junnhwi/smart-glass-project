from __future__ import annotations

import unittest

from src.modules.auth.security import (
    AuthSecurityService,
    RateLimitExceededError,
    RateLimitPolicy,
)


class FakeAuthSecurityRepository:
    def __init__(self) -> None:
        self.events: list[dict[str, object | None]] = []

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
    ) -> None:
        self.events.append(
            {
                "event_type": event_type,
                "outcome": outcome,
                "user_id": user_id,
                "email": email,
                "provider": provider,
                "device_id": device_id,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "metadata_json": metadata_json,
            }
        )


class AuthSecurityServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = FakeAuthSecurityRepository()
        self.service = AuthSecurityService(
            self.repository,
            policies={
                "auth.login.ip": RateLimitPolicy(
                    key="auth.login.ip",
                    max_attempts=2,
                    window_sec=60,
                )
            },
        )

    def test_rate_limit_blocks_third_attempt_within_window(self) -> None:
        self.service.enforce_rate_limit(
            policy_key="auth.login.ip",
            identifier="127.0.0.1",
        )
        self.service.enforce_rate_limit(
            policy_key="auth.login.ip",
            identifier="127.0.0.1",
        )

        with self.assertRaises(RateLimitExceededError):
            self.service.enforce_rate_limit(
                policy_key="auth.login.ip",
                identifier="127.0.0.1",
            )

    def test_record_event_serializes_metadata(self) -> None:
        self.service.record_event(
            event_type="auth.login",
            outcome="failed",
            email="user@example.com",
            ip_address="127.0.0.1",
            metadata={"error": "Invalid email or password"},
        )

        self.assertEqual(len(self.repository.events), 1)
        event = self.repository.events[0]
        self.assertEqual(event["event_type"], "auth.login")
        self.assertEqual(event["outcome"], "failed")
        self.assertIn("Invalid email or password", str(event["metadata_json"]))


if __name__ == "__main__":
    unittest.main()
