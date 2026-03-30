import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python http_healthcheck.py <url>", file=sys.stderr)
        return 2

    url = sys.argv[1]

    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            status_code = response.getcode()
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        print(f"Healthcheck request failed: {exc}", file=sys.stderr)
        return 1

    if status_code < 200 or status_code >= 300:
        print(f"Healthcheck returned non-2xx status: {status_code}", file=sys.stderr)
        return 1

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        print("Healthcheck response is not valid JSON", file=sys.stderr)
        return 1

    if payload.get("status") not in {"ok", "degraded"}:
        print(f"Unexpected health status: {payload.get('status')}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
