#!/usr/bin/env python
from __future__ import annotations

from pathlib import Path
import json
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / ".env"
APP_JSON_PATH = REPO_ROOT / "apps" / "smart-glass-client" / "app.json"
CLIENT_ENV_PATH = REPO_ROOT / "apps" / "smart-glass-client" / ".env"
CLIENT_ENV_LOCAL_PATH = REPO_ROOT / "apps" / "smart-glass-client" / ".env.local"

REQUIRED_ENV_KEYS = [
    "API_CAPTURE_DATABASE_URL",
    "API_AUTH_JWT_SECRET",
    "API_AUTH_GOOGLE_CLIENT_ID",
    "API_AUTH_GOOGLE_CLIENT_SECRET",
    "API_AUTH_GOOGLE_CALLBACK_URL",
]

OPTIONAL_ENV_KEYS = [
    "API_AUTH_ENABLE_DEMO_TOKENS",
]


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_app_scheme(path: Path) -> str | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    expo = payload.get("expo") or {}
    scheme = expo.get("scheme")
    if isinstance(scheme, str) and scheme.strip():
        return scheme.strip()
    return None


def print_line(message: str = "") -> None:
    print(message, flush=True)


def main() -> int:
    env_values = load_dotenv(ENV_PATH)
    client_env_values = load_dotenv(CLIENT_ENV_PATH)
    client_env_local_values = load_dotenv(CLIENT_ENV_LOCAL_PATH)
    app_scheme = load_app_scheme(APP_JSON_PATH)
    client_api_base_url = (
        client_env_local_values.get("EXPO_PUBLIC_API_BASE_URL", "").strip()
        or client_env_values.get("EXPO_PUBLIC_API_BASE_URL", "").strip()
    )

    missing_required = [
        key for key in REQUIRED_ENV_KEYS if not env_values.get(key, "").strip()
    ]

    print_line("Google OAuth local readiness check")
    print_line("=" * 40)
    print_line(f"repo: {REPO_ROOT}")
    print_line(f".env: {'found' if ENV_PATH.is_file() else 'missing'}")
    print_line(
        "client env: "
        + (
            ".env.local found"
            if CLIENT_ENV_LOCAL_PATH.is_file()
            else ".env found"
            if CLIENT_ENV_PATH.is_file()
            else "missing"
        )
    )
    print_line(f"app scheme: {app_scheme or 'missing'}")
    print_line()

    print_line("Required environment values")
    for key in REQUIRED_ENV_KEYS:
        status = "OK" if env_values.get(key, "").strip() else "MISSING"
        print_line(f"- {key}: {status}")

    print_line()
    print_line("Optional environment values")
    for key in OPTIONAL_ENV_KEYS:
        status = "SET" if env_values.get(key, "").strip() else "EMPTY"
        print_line(f"- {key}: {status}")
    print_line(
        f"- EXPO_PUBLIC_API_BASE_URL: {'SET' if client_api_base_url else 'EMPTY'}"
    )

    callback_url = env_values.get("API_AUTH_GOOGLE_CALLBACK_URL", "").strip()
    if callback_url:
        print_line()
        print_line("Google Console redirect URI")
        print_line(f"- {callback_url}")

    if client_api_base_url:
        print_line()
        print_line("Expo client API base URL")
        print_line(f"- {client_api_base_url}")

    print_line()
    print_line("Recommended first test path")
    print_line("- Start backend on http://localhost:8002")
    print_line("- Run Expo with --web")
    print_line("- Click 'Continue with Google' from the login screen")

    if app_scheme:
        print_line()
        print_line("Native deep-link target")
        print_line(f"- {app_scheme}://oauth")
        print_line("- Prefer a development build for native OAuth testing")

    print_line()
    if missing_required:
        print_line("Result: NOT READY")
        print_line("Missing required values:")
        for key in missing_required:
            print_line(f"- {key}")
        return 1

    if not client_api_base_url:
        print_line("Result: BACKEND READY, CLIENT ENV INCOMPLETE")
        print_line("Missing client value:")
        print_line("- EXPO_PUBLIC_API_BASE_URL in apps/smart-glass-client/.env.local")
        return 1

    print_line("Result: READY FOR CONFIGURED WEB TEST")
    print_line(
        "If Google Console redirect URI and test users are configured correctly, "
        "you can try a real sign-in."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
