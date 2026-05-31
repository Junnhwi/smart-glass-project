from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[1]
AI_TEST_DIR = Path(__file__).resolve().parent
INFERENCE_APP_DIR = ROOT_DIR / "apps" / "inference-server"
DEFAULT_IMAGE_PATH = AI_TEST_DIR / "esp640x480.jfif"
DEFAULT_OUTPUT_PATH = AI_TEST_DIR / "vlm_result.json"
DEFAULT_GENERATION_OUTPUT_PATH = AI_TEST_DIR / "vlm_generation_result.json"
DEFAULT_VLM_MODEL = "gemma4:31b-cloud"


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


def _utc_now_isoformat() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _configure_ollama_env(args: argparse.Namespace) -> None:
    if args.base_url:
        os.environ["OLLAMA_API_URL"] = args.base_url
    elif _env_value("OLLAMA_API_URL"):
        os.environ["OLLAMA_API_URL"] = _env_value("OLLAMA_API_URL")
    elif _env_value("API_LLM_OLLAMA_BASE_URL"):
        os.environ["OLLAMA_API_URL"] = _env_value("API_LLM_OLLAMA_BASE_URL")

    if args.model:
        os.environ["OLLAMA_VLM_MODEL"] = args.model
    elif _env_value("OLLAMA_VLM_MODEL"):
        os.environ["OLLAMA_VLM_MODEL"] = _env_value("OLLAMA_VLM_MODEL")
    elif _env_value("OLLAMA_MODEL"):
        os.environ["OLLAMA_VLM_MODEL"] = _env_value("OLLAMA_MODEL")
    else:
        os.environ["OLLAMA_VLM_MODEL"] = DEFAULT_VLM_MODEL

    if args.api_key:
        os.environ["OLLAMA_API_KEY"] = args.api_key
    elif _env_value("OLLAMA_API_KEY"):
        os.environ["OLLAMA_API_KEY"] = _env_value("OLLAMA_API_KEY")
    elif _env_value("API_LLM_OLLAMA_API_KEY"):
        os.environ["OLLAMA_API_KEY"] = _env_value("API_LLM_OLLAMA_API_KEY")

    if args.timeout_sec:
        os.environ["OLLAMA_TIMEOUT_SEC"] = str(args.timeout_sec)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run the same Ollama VLM adapter path used by process_vision_inference "
            "against a local image, then save the worker-style result JSON."
        )
    )
    parser.add_argument("--image", type=Path, default=DEFAULT_IMAGE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--generation-output",
        type=Path,
        default=DEFAULT_GENERATION_OUTPUT_PATH,
    )
    parser.add_argument("--base-url", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--timeout-sec", type=int, default=0)
    parser.add_argument("--user-id", default="ai-test2-user")
    parser.add_argument("--memory-id", default="ai-test2-memory-001")
    parser.add_argument("--request-id", default="ai-test2-request-001")
    parser.add_argument("--task-type", default="caption")
    parser.add_argument("--image-key", default="")
    parser.add_argument("--image-url", default="")
    parser.add_argument("--captured-at", default="")
    args = parser.parse_args()

    image_path = args.image.resolve()
    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")

    _configure_ollama_env(args)
    sys.path.insert(0, str(INFERENCE_APP_DIR))

    from src.adapters.ollama_adapter import generate_ollama_vlm_metadata
    from src.contracts.vlm import build_vlm_error_result, build_vlm_success_result

    image_key = args.image_key or str(image_path.relative_to(ROOT_DIR)).replace("\\", "/")
    captured_at = args.captured_at or _utc_now_isoformat()

    try:
        with Image.open(image_path) as raw_image:
            generation_result = generate_ollama_vlm_metadata(image=raw_image.convert("RGB"))
    except Exception as exc:
        worker_result = build_vlm_error_result(
            request_id=args.request_id,
            user_id=args.user_id,
            image_key=image_key,
            error=exc,
            model_key=os.getenv("OLLAMA_VLM_MODEL", "ollama-vl"),
            quantization="none",
            dtype_name="float16",
            memory_id=args.memory_id,
            image_url=args.image_url or None,
            captured_at=captured_at,
            task_type=args.task_type,
            content_type="image/jpeg",
            error_code="ollama_vlm_experiment_failed",
            retryable=True,
            execution_policy=None,
            error_details={
                "category": "ollama",
                "reason": "ollama_vlm_experiment_failed",
                "exceptionType": type(exc).__name__,
                "retryable": True,
                "source": "ai_test2.run_vlm_ollama_pipeline",
            },
            runtime_metrics={},
        )
        _write_json(args.output, worker_result)
        print(f"Saved worker error result: {args.output}")
        print(json.dumps(worker_result, ensure_ascii=False, indent=2))
        raise SystemExit(1) from exc

    _write_json(args.generation_output, generation_result)

    worker_result = build_vlm_success_result(
        request_id=args.request_id,
        user_id=args.user_id,
        image_key=image_key,
        model_key=generation_result.get("model_key") or "ollama-vl",
        quantization=generation_result.get("quantization") or "none",
        dtype_name="float16",
        generation_result=generation_result,
        memory_id=args.memory_id,
        image_url=args.image_url or None,
        captured_at=captured_at,
        task_type=args.task_type,
        content_type="image/jpeg",
        inference_metadata=generation_result.get("metadata"),
        pipeline_output=generation_result.get("pipeline_output"),
        execution_policy=None,
        runtime_metrics={
            "modelInferenceSec": generation_result.get("elapsed_sec") or 0.0,
            "taskLatencySec": generation_result.get("elapsed_sec") or 0.0,
        },
    )
    _write_json(args.output, worker_result)

    print(f"Saved generation result: {args.generation_output}")
    print(f"Saved worker result: {args.output}")
    print(json.dumps(worker_result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
