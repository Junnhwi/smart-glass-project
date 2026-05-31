from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

try:
    import psycopg
except ImportError as exc:  # pragma: no cover - runtime helper
    raise SystemExit(
        "psycopg is required. Install apps/api-server requirements first: "
        "pip install -r apps/api-server/requirements.txt"
    ) from exc


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output" / "llm-memory-dump"
DEFAULT_LOCAL_DATABASE_URL = (
    "postgresql://api_server:api_server@localhost:5432/smart_glass"
)


def _load_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _host_runnable_database_url(database_url: str) -> str:
    parsed = urlparse(database_url)
    if parsed.hostname != "postgres":
        return database_url
    netloc = parsed.netloc.replace("@postgres:", "@localhost:", 1)
    return urlunparse(parsed._replace(netloc=netloc))


def _database_url_from_args(args: argparse.Namespace) -> str:
    if args.database_url:
        return args.database_url

    dotenv_values = _load_dotenv(ROOT_DIR / ".env")
    database_url = (
        os.getenv("API_CAPTURE_DATABASE_URL")
        or dotenv_values.get("API_CAPTURE_DATABASE_URL")
        or DEFAULT_LOCAL_DATABASE_URL
    ).strip()
    return _host_runnable_database_url(database_url)


def _safe_file_part(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_.-]+", "_", value.strip())
    return cleaned.strip("_") or "memory"


def _write_record(output_dir: Path, document: dict[str, Any]) -> Path:
    user_id = _safe_file_part(str(document.get("user_id") or "unknown-user"))
    memory_id = _safe_file_part(str(document.get("memory_id") or "unknown-memory"))
    output_path = output_dir / f"{user_id}__{memory_id}.json"
    output_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def dump_records(
    *,
    database_url: str,
    output_dir: Path,
    user_id: str | None,
    limit: int | None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    query = """
        SELECT document::text
        FROM memory_records
    """
    params: list[Any] = []
    if user_id:
        query += " WHERE user_id = %s"
        params.append(user_id)
    query += " ORDER BY (captured_at IS NULL) ASC, captured_at DESC, memory_id DESC"
    if limit:
        query += " LIMIT %s"
        params.append(limit)

    written: list[Path] = []
    with psycopg.connect(database_url, connect_timeout=5) as conn:
        with conn.cursor() as cur:
            cur.execute(query, tuple(params))
            for (document_json,) in cur.fetchall():
                written.append(_write_record(output_dir, json.loads(document_json)))
    return written


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dump stored memory_records.document JSONB rows for LLM-only experiments."
    )
    parser.add_argument("--database-url", help="Override API_CAPTURE_DATABASE_URL.")
    parser.add_argument("--user-id", help="Dump only one user's memories.")
    parser.add_argument("--limit", type=int, help="Maximum number of rows to dump.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for dumped JSON files. Default: {DEFAULT_OUTPUT_DIR}",
    )
    args = parser.parse_args()

    try:
        written = dump_records(
            database_url=_database_url_from_args(args),
            output_dir=args.output_dir,
            user_id=args.user_id,
            limit=args.limit,
        )
    except Exception as exc:
        raise SystemExit(
            "Failed to dump memory records. Check that PostgreSQL is running and "
            "API_CAPTURE_DATABASE_URL points to a host reachable from this shell. "
            f"Details: {exc}"
        ) from exc
    print(f"Dumped {len(written)} memory JSON file(s) to {args.output_dir}")


if __name__ == "__main__":
    main()
