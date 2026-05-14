#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEMO_AUTH_TOKEN_PREFIX = "demo-user:"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8002"
DEFAULT_IMAGE_PATH = "apps/inference-server/sample_data/KakaoTalk_20260406_114213285.png"
DEFAULT_QUERY_BY_STEM = {
    "wallet": "wallet",
    "key": "key",
    "keys": "key",
}
METADATA_QUERY_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "is",
    "it",
    "near",
    "next",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
    "있다",
    "있는",
    "위",
    "옆",
    "근처",
    "사진",
    "장면",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the device-auth capture smoke flow against api-server: "
            "user registration, device registration, upload authorization, "
            "direct upload, capture registration, task polling, and chat/search validation."
        )
    )
    parser.add_argument(
        "image_path",
        nargs="?",
        default=DEFAULT_IMAGE_PATH,
        help=f"Image file to upload. Defaults to {DEFAULT_IMAGE_PATH}",
    )
    parser.add_argument(
        "--api-base-url",
        default=DEFAULT_API_BASE_URL,
        help=f"Base URL for api-server. Default: {DEFAULT_API_BASE_URL}",
    )
    parser.add_argument(
        "--user-id",
        default="device-auth-smoke-user",
        help="User id to create or reuse for the smoke flow.",
    )
    parser.add_argument(
        "--device-id",
        default="device-auth-smoke-glass-001",
        help="Device id to register or reuse for the smoke flow.",
    )
    parser.add_argument(
        "--query",
        default="",
        help=(
            "Search/chat query to verify stored memory. When omitted, the script "
            "uses metadata stored from the actual VLM result instead of the image file name."
        ),
    )
    parser.add_argument(
        "--poll-timeout-sec",
        type=int,
        default=180,
        help="Maximum seconds to wait for the worker task to finish. Default: 180",
    )
    parser.add_argument(
        "--poll-interval-sec",
        type=float,
        default=5.0,
        help="Polling interval in seconds for /media/captures/tasks/{taskId}. Default: 5",
    )
    return parser.parse_args()


def infer_query(image_path: Path, explicit_query: str) -> str:
    normalized = explicit_query.strip()
    if normalized:
        return normalized

    stem = image_path.stem.lower()
    for token, query in DEFAULT_QUERY_BY_STEM.items():
        if token in stem:
            return query
    return stem.replace("_", " ").replace("-", " ").strip() or "photo"


def normalize_query_candidate(value: Any) -> str:
    normalized = " ".join(str(value or "").replace("_", " ").replace("-", " ").split())
    return normalized.strip(" ,.;:()[]{}\"'")


def append_candidate(candidates: list[str], value: Any) -> None:
    candidate = normalize_query_candidate(value)
    if not candidate:
        return
    lowered = candidate.lower()
    if lowered in METADATA_QUERY_STOPWORDS:
        return
    if len(candidate) <= 1 and not ("\uac00" <= candidate <= "\ud7a3"):
        return
    if candidate not in candidates:
        candidates.append(candidate)


def append_text_candidates(candidates: list[str], value: Any, *, max_terms: int = 8) -> None:
    text = normalize_query_candidate(value)
    if not text:
        return

    append_candidate(candidates, text)
    for raw_token in text.replace("/", " ").split():
        token = normalize_query_candidate(raw_token)
        if len(token) < 2:
            continue
        append_candidate(candidates, token)
        if len(candidates) >= max_terms:
            break


def metadata_query_candidates(memory_item: dict[str, Any] | None) -> list[str]:
    candidates: list[str] = []
    if not memory_item:
        return candidates

    for field_name in ("detectedObjects", "tags"):
        values = memory_item.get(field_name) or []
        if not isinstance(values, list):
            continue
        for value in values:
            append_candidate(candidates, value)

    append_text_candidates(candidates, memory_item.get("positionHint"), max_terms=12)
    location = memory_item.get("location") or {}
    if isinstance(location, dict):
        append_candidate(candidates, location.get("name"))
        append_candidate(candidates, location.get("address"))

    append_text_candidates(candidates, memory_item.get("caption"), max_terms=18)
    append_text_candidates(candidates, memory_item.get("sceneSummary"), max_terms=24)
    return candidates


def hit_memory_ids(search_payload: dict[str, Any]) -> set[str]:
    hits = search_payload.get("hits") or []
    if not isinstance(hits, list):
        return set()
    return {
        str(hit.get("memoryId") or "").strip()
        for hit in hits
        if isinstance(hit, dict) and str(hit.get("memoryId") or "").strip()
    }


def choose_metadata_query(
    *,
    api_base_url: str,
    user_id: str,
    headers: dict[str, str],
    target_memory_id: str,
    explicit_query: str,
    fallback_query: str,
) -> tuple[str, dict[str, Any], dict[str, Any] | None, list[str]]:
    recent_status, recent_payload = http_get_json(
        f"{api_base_url}/memories/recent?"
        + urllib.parse.urlencode({"userId": user_id, "limit": "10"}),
        headers=headers,
    )
    recent_result = require_success(
        recent_status,
        recent_payload,
        "recent memory metadata lookup",
    )
    recent_items = recent_result.get("items") or []
    target_memory = None
    if isinstance(recent_items, list):
        for item in recent_items:
            if not isinstance(item, dict):
                continue
            if str(item.get("memoryId") or "").strip() == target_memory_id:
                target_memory = item
                break
        if target_memory is None and recent_items:
            first_item = recent_items[0]
            if isinstance(first_item, dict):
                target_memory = first_item

    candidates: list[str] = []
    append_candidate(candidates, explicit_query)
    for candidate in metadata_query_candidates(target_memory):
        append_candidate(candidates, candidate)
    append_candidate(candidates, fallback_query)

    search_attempts: list[dict[str, Any]] = []
    for candidate in candidates:
        search_status, search_payload = http_json(
            "POST",
            f"{api_base_url}/search",
            payload={"userId": user_id, "query": candidate, "topK": 3},
            headers=headers,
        )
        search_result = require_success(
            search_status,
            search_payload,
            f"search validation for query {candidate!r}",
        )
        search_attempts.append(
            {
                "query": candidate,
                "totalHits": search_result.get("totalHits"),
                "memoryIds": sorted(hit_memory_ids(search_result)),
            }
        )
        if int(search_result.get("totalHits") or 0) <= 0:
            continue
        if not target_memory_id or target_memory_id in hit_memory_ids(search_result):
            return candidate, search_result, target_memory, candidates

    raise RuntimeError(
        "search returned zero relevant hits after successful memory store. "
        "Tried metadata-derived queries:\n"
        + json.dumps(search_attempts, ensure_ascii=False, indent=2)
    )


def infer_content_type(image_path: Path) -> str:
    content_type, _ = mimetypes.guess_type(str(image_path))
    return content_type or "image/jpeg"


def print_step(message: str) -> None:
    print(f"[device-auth-smoke] {message}", flush=True)


def http_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any]]:
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)

    body: bytes | None = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            parsed = json.loads(raw) if raw else {}
            return response.status, parsed
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = {"detail": raw}
        return exc.code, parsed


def http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, dict[str, Any]]:
    return http_json("GET", url, headers=headers, timeout=timeout)


def put_file(upload_url: str, image_path: Path, *, content_type: str) -> None:
    request = urllib.request.Request(
        upload_url,
        data=image_path.read_bytes(),
        headers={"Content-Type": content_type},
        method="PUT",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"Upload failed with {response.status}")


def require_success(status_code: int, payload: dict[str, Any], message: str) -> dict[str, Any]:
    if 200 <= status_code < 300:
        return payload
    detail = payload.get("detail") or payload
    raise RuntimeError(f"{message} failed: HTTP {status_code} {detail}")


def bearer_headers(user_id: str) -> dict[str, str]:
    token = f"{DEMO_AUTH_TOKEN_PREFIX}{user_id}"
    return {"Authorization": f"Bearer {token}"}


def main() -> int:
    args = parse_args()
    image_path = Path(args.image_path).expanduser().resolve()
    if not image_path.is_file():
        raise SystemExit(f"image file not found: {image_path}")

    api_base_url = args.api_base_url.rstrip("/")
    user_id = args.user_id.strip()
    device_id = args.device_id.strip()
    if not user_id:
        raise SystemExit("--user-id must not be blank")
    if not device_id:
        raise SystemExit("--device-id must not be blank")

    fallback_query = infer_query(image_path, "")
    explicit_query = args.query.strip()
    content_type = infer_content_type(image_path)

    print_step(f"image={image_path}")
    print_step(
        f"user_id={user_id} device_id={device_id} "
        f"query={'metadata-derived' if not explicit_query else explicit_query!r}"
    )

    health_status, health_payload = http_get_json(f"{api_base_url}/health/ready")
    require_success(health_status, health_payload, "api-server readiness check")
    print_step("api-server is ready")

    create_status, create_payload = http_json(
        "POST",
        f"{api_base_url}/users",
        payload={"userId": user_id},
    )
    require_success(create_status, create_payload, "user creation")
    print_step("user created or confirmed")

    register_status, register_payload = http_json(
        "POST",
        f"{api_base_url}/users/{urllib.parse.quote(user_id, safe='')}/devices",
        payload={"deviceId": device_id},
    )
    require_success(register_status, register_payload, "device registration")
    print_step("device registered or confirmed")

    authorize_status, authorize_payload = http_json(
        "POST",
        f"{api_base_url}/media/upload-authorizations",
        payload={
            "deviceId": device_id,
            "fileName": image_path.name,
            "contentType": content_type,
        },
    )
    authorization = require_success(
        authorize_status,
        authorize_payload,
        "upload authorization",
    )
    upload = authorization.get("upload") or {}
    upload_url = str(upload.get("uploadUrl") or "").strip()
    source_image = upload.get("sourceImage") or {}
    image_key = str(source_image.get("imageKey") or "").strip()
    if authorization.get("status") != "allowed" or not authorization.get("userId"):
        raise RuntimeError(f"device authorization was not allowed: {authorization}")
    if not upload_url:
        raise RuntimeError(f"uploadUrl missing from authorization response: {authorization}")
    if not image_key:
        raise RuntimeError(f"imageKey missing from authorization response: {authorization}")
    print_step(f"authorized upload image_key={image_key}")

    put_file(upload_url, image_path, content_type=content_type)
    print_step("direct upload completed")

    capture_payload = {
        "captureId": upload.get("captureId"),
        "requestId": upload.get("requestId"),
        "memoryId": upload.get("memoryId"),
        "userId": authorization["userId"],
        "deviceId": authorization["deviceId"],
        "taskType": upload.get("taskType"),
        "capturedAt": upload.get("capturedAt"),
        "sourceImage": source_image,
    }
    capture_status, capture_response = http_json(
        "POST",
        f"{api_base_url}/media/captures",
        payload=capture_payload,
    )
    accepted = require_success(capture_status, capture_response, "capture registration")
    task_id = str(accepted.get("taskId") or "").strip()
    if not task_id:
        raise RuntimeError(f"taskId missing from capture response: {accepted}")
    print_step(f"capture accepted task_id={task_id}")

    deadline = time.time() + max(1, args.poll_timeout_sec)
    task_status_payload: dict[str, Any] | None = None
    while time.time() < deadline:
        poll_status, poll_payload = http_get_json(
            f"{api_base_url}/media/captures/tasks/{urllib.parse.quote(task_id, safe='')}"
        )
        require_success(poll_status, poll_payload, "capture task polling")
        task_status_payload = poll_payload
        status_text = str(poll_payload.get("status") or "")
        worker_status = str((poll_payload.get("worker") or {}).get("status") or "")
        print_step(f"task_status={status_text} worker_status={worker_status}")

        if status_text in {"completed", "partial", "failed"}:
            break
        time.sleep(max(0.5, args.poll_interval_sec))

    if task_status_payload is None:
        raise RuntimeError("task polling did not return any payload")

    final_status = str(task_status_payload.get("status") or "")
    memory_store = task_status_payload.get("memoryStore") or {}
    if final_status != "completed":
        raise RuntimeError(
            "capture task did not complete successfully:\n"
            + json.dumps(task_status_payload, ensure_ascii=False, indent=2)
        )
    if memory_store.get("status") != "success":
        raise RuntimeError(
            "memory store did not succeed:\n"
            + json.dumps(task_status_payload, ensure_ascii=False, indent=2)
        )
    print_step("worker completed and memory was stored")

    headers = bearer_headers(user_id)
    target_memory_id = str(upload.get("memoryId") or capture_payload.get("memoryId") or "").strip()
    query, search_result, target_memory, query_candidates = choose_metadata_query(
        api_base_url=api_base_url,
        user_id=user_id,
        headers=headers,
        target_memory_id=target_memory_id,
        explicit_query=explicit_query,
        fallback_query=fallback_query,
    )
    print_step(
        f"search validation passed query={query!r} "
        f"total_hits={search_result['totalHits']}"
    )

    chat_status, chat_payload = http_json(
        "POST",
        f"{api_base_url}/chat",
        payload={"userId": user_id, "query": query, "topK": 3},
        headers=headers,
    )
    chat_result = require_success(chat_status, chat_payload, "chat validation")
    answer = str(chat_result.get("answer") or "").strip()
    if not answer:
        raise RuntimeError(
            "chat returned an empty answer:\n"
            + json.dumps(chat_result, ensure_ascii=False, indent=2)
        )
    print_step("chat validation passed")

    summary = {
        "userId": user_id,
        "deviceId": device_id,
        "query": query,
        "querySource": "explicit" if explicit_query else "stored_metadata",
        "queryCandidates": query_candidates,
        "imagePath": str(image_path),
        "imageKey": image_key,
        "memoryId": target_memory_id,
        "storedMetadata": target_memory,
        "taskId": task_id,
        "taskStatus": final_status,
        "memoryStoreStatus": memory_store.get("status"),
        "searchTotalHits": search_result.get("totalHits"),
        "chatAnswer": answer,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit("cancelled by user")
    except Exception as exc:
        print(f"[device-auth-smoke] ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
