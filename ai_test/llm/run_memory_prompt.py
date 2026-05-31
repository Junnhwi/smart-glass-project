from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from urllib import request


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MEMORY_DIR = ROOT_DIR / "output" / "llm-memory-dump"
DEFAULT_PROMPT_FILE = Path(__file__).with_name("answer_prompt.txt")
SYSTEM_PROMPT = (
    "You are a smart assistant that helps the user find their belongings. "
    "Always respond in Korean."
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


def _env_value(key: str, default: str = "") -> str:
    dotenv_values = _load_dotenv(ROOT_DIR / ".env")
    return (os.getenv(key) or dotenv_values.get(key) or default).strip()


def _load_memory_documents(memory_dir: Path, limit: int | None) -> list[dict[str, Any]]:
    files = sorted(memory_dir.glob("*.json"))
    documents: list[dict[str, Any]] = []
    for path in files:
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Skipping unreadable JSON file {path}: {exc}")
            continue
        if isinstance(document, dict):
            documents.append(document)

    documents.sort(
        key=lambda item: (
            item.get("captured_at") is None,
            str(item.get("captured_at") or ""),
            str(item.get("memory_id") or ""),
        ),
        reverse=True,
    )
    return documents[:limit] if limit else documents


def _format_memory(document: dict[str, Any], index: int) -> str:
    location = document.get("location") or {}
    if not isinstance(location, dict):
        location = {}
    location_text = (
        location.get("name")
        or location.get("address")
        or "Unknown"
    )
    return "\n".join(
        [
            f"[Memory {index}]",
            f"- Image Key: {document.get('image_key') or 'No image'}",
            f"- Captured At: {document.get('captured_at') or 'Unknown'}",
            f"- Location: {location_text}",
            f"- Position Hint: {document.get('position_hint') or 'None'}",
            "- Detected Objects: "
            + (", ".join(document.get("detected_objects") or []) or "None"),
            "- Tags: " + (", ".join(document.get("tags") or []) or "None"),
            f"- Caption: {document.get('caption') or 'None'}",
            f"- Scene Summary: {document.get('scene_summary') or 'None'}",
        ]
    )


def _build_messages(
    *,
    question: str,
    documents: list[dict[str, Any]],
    prompt_template: str,
) -> list[dict[str, str]]:
    context = "\n\n".join(
        _format_memory(document, index + 1)
        for index, document in enumerate(documents)
    )
    user_prompt = prompt_template.format(
        question=question,
        context=context or "No memory records.",
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def _ollama_chat(
    *,
    base_url: str,
    model: str,
    api_key: str | None,
    messages: list[dict[str, str]],
    temperature: float,
    timeout_sec: int,
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": 512,
        },
    }
    url = f"{base_url.rstrip('/')}/chat"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with request.urlopen(req, timeout=timeout_sec) as response:
        body = json.loads(response.read().decode("utf-8"))
    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, dict) or not message.get("content"):
        raise RuntimeError(f"Unexpected Ollama response: {body}")
    return str(message["content"]).strip()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run LLM-only answer prompt experiments from dumped memory JSON."
    )
    parser.add_argument("question", help="Question to ask against memory JSON.")
    parser.add_argument(
        "--memory-dir",
        type=Path,
        default=DEFAULT_MEMORY_DIR,
        help=f"Directory containing dumped memory JSON. Default: {DEFAULT_MEMORY_DIR}",
    )
    parser.add_argument(
        "--prompt-file",
        type=Path,
        default=DEFAULT_PROMPT_FILE,
        help=f"Prompt template file. Default: {DEFAULT_PROMPT_FILE}",
    )
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--base-url",
        default=_env_value("API_LLM_OLLAMA_BASE_URL", "http://127.0.0.1:11434/api"),
    )
    parser.add_argument(
        "--model",
        default=_env_value("API_LLM_OLLAMA_MODEL", "gemma3:4b"),
    )
    parser.add_argument(
        "--api-key",
        default=_env_value("API_LLM_OLLAMA_API_KEY"),
    )
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the built messages instead of calling the LLM.",
    )
    args = parser.parse_args()

    documents = _load_memory_documents(args.memory_dir, args.limit)
    prompt_template = args.prompt_file.read_text(encoding="utf-8")
    messages = _build_messages(
        question=args.question,
        documents=documents,
        prompt_template=prompt_template,
    )

    if args.dry_run:
        print(json.dumps(messages, ensure_ascii=False, indent=2))
        return

    answer = _ollama_chat(
        base_url=args.base_url,
        model=args.model,
        api_key=args.api_key or None,
        messages=messages,
        temperature=args.temperature,
        timeout_sec=args.timeout_sec,
    )
    print(answer)


if __name__ == "__main__":
    main()
