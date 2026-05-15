import io
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from celery import Celery
from celery.exceptions import Retry, SoftTimeLimitExceeded
from celery.signals import worker_init
from PIL import Image, UnidentifiedImageError

from src.contracts.vlm import (
    build_request_id,
    build_vlm_error_result,
    build_vlm_success_result,
)
from src.core.logging import configure_logging, get_logger
from src.models.captioning import generate_caption
from src.models.qwen_vlm import generate_qwen_vlm_metadata
from src.adapters.ollama_adapter import generate_ollama_vlm_metadata
from src.models.registry import resolve_inference_model
from src.models.serving_profile import (
    resolve_runtime_execution_policy,
    resolve_task_time_limits,
)
from src.storage.s3 import (
    StorageAccessError,
    StorageConfigError,
    StorageNotFoundError,
    get_storage_service,
)
from src.worker_preload import maybe_preload_on_startup

broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
result_backend = os.getenv("CELERY_RESULT_BACKEND", broker_url)
app = Celery("inference_tasks", broker=broker_url, backend=result_backend)

TASK_SOFT_TIME_LIMIT_SECONDS, TASK_TIME_LIMIT_SECONDS = resolve_task_time_limits()


def _nonnegative_int_env(name: str, fallback: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        return max(0, int(raw))
    except ValueError:
        return fallback


def _positive_float_env(name: str, fallback: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        return max(1.0, float(raw))
    except ValueError:
        return fallback


TASK_MAX_RETRIES = _nonnegative_int_env("VISION_TASK_MAX_RETRIES", 2)
TASK_RETRY_DELAY_SECONDS = _nonnegative_int_env("VISION_TASK_RETRY_DELAY_SEC", 10)
TASK_RETRY_BACKOFF_MULTIPLIER = _positive_float_env(
    "VISION_TASK_RETRY_BACKOFF_MULTIPLIER",
    2.0,
)
TASK_RETRY_MAX_DELAY_SECONDS = _nonnegative_int_env(
    "VISION_TASK_RETRY_MAX_DELAY_SEC",
    max(TASK_RETRY_DELAY_SECONDS, 60),
)

app.conf.update(
    task_track_started=True,
    result_expires=3600,
    task_soft_time_limit=TASK_SOFT_TIME_LIMIT_SECONDS,
    task_time_limit=TASK_TIME_LIMIT_SECONDS,
)
configure_logging()
logger = get_logger(__name__)


@dataclass(frozen=True)
class InferenceFailurePolicy:
    error_code: str
    retryable: bool
    category: str


@worker_init.connect
def _preload_worker_model_on_startup(**_: object) -> None:
    maybe_preload_on_startup()


def _should_retry_with_qwen_fallback(error: Exception) -> bool:
    message = str(error).lower()
    retryable_markers = (
        "out of memory",
        "cuda error",
        "cublas",
        "device-side assert",
        "allocation",
    )
    return any(marker in message for marker in retryable_markers)


def _classify_inference_error(error: Exception) -> InferenceFailurePolicy:
    if isinstance(error, (SoftTimeLimitExceeded, TimeoutError)):
        return InferenceFailurePolicy("inference_timeout", True, "timeout")
    if isinstance(error, StorageNotFoundError):
        return InferenceFailurePolicy("source_image_not_found", False, "source_image")
    if isinstance(error, StorageConfigError):
        return InferenceFailurePolicy("storage_config_error", False, "storage")
    if isinstance(error, StorageAccessError):
        return InferenceFailurePolicy("storage_access_error", True, "storage")
    if isinstance(error, UnidentifiedImageError):
        return InferenceFailurePolicy("invalid_source_image", False, "input")
    if isinstance(error, ValueError):
        return InferenceFailurePolicy("invalid_inference_request", False, "input")
    if isinstance(error, RuntimeError):
        return InferenceFailurePolicy("model_runtime_error", True, "model")
    return InferenceFailurePolicy("inference_task_error", True, "unknown")


def _build_error_details(
    *,
    error: Exception,
    failure_policy: InferenceFailurePolicy,
) -> dict[str, object]:
    return {
        "category": failure_policy.category,
        "reason": failure_policy.error_code,
        "exceptionType": type(error).__name__,
        "retryable": failure_policy.retryable,
        "source": "inference_worker",
        "taskTimeLimit": {
            "softSec": TASK_SOFT_TIME_LIMIT_SECONDS,
            "hardSec": TASK_TIME_LIMIT_SECONDS,
        },
    }


def _elapsed_sec(started_at: float) -> float:
    return round(max(0.0, time.perf_counter() - started_at), 4)


def _parse_enqueued_at(value: object | None) -> datetime | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _queue_wait_sec(enqueued_at: object | None) -> float | None:
    parsed = _parse_enqueued_at(enqueued_at)
    if parsed is None:
        return None
    elapsed = (datetime.now(timezone.utc) - parsed).total_seconds()
    return round(max(0.0, elapsed), 4)


def _build_task_runtime_metrics(
    *,
    task_started_at: float,
    queue_wait_sec: float | None,
    storage_read_sec: float | None,
    image_decode_sec: float | None,
    model_inference_sec: float | None,
) -> dict[str, float]:
    metrics = {
        "taskLatencySec": _elapsed_sec(task_started_at),
    }
    optional_metrics = {
        "queueWaitSec": queue_wait_sec,
        "storageReadSec": storage_read_sec,
        "imageDecodeSec": image_decode_sec,
        "modelInferenceSec": model_inference_sec,
    }
    for key, value in optional_metrics.items():
        if value is not None:
            metrics[key] = value
    return metrics


def _log_runtime_metrics(runtime_metrics: dict[str, float]) -> dict[str, float | None]:
    return {
        "queue_wait_sec": runtime_metrics.get("queueWaitSec"),
        "storage_read_sec": runtime_metrics.get("storageReadSec"),
        "image_decode_sec": runtime_metrics.get("imageDecodeSec"),
        "model_inference_sec": runtime_metrics.get("modelInferenceSec"),
        "task_latency_sec": runtime_metrics["taskLatencySec"],
    }


def _task_called_directly(task_request: object | None) -> bool:
    return bool(getattr(task_request, "called_directly", False))


def _task_retry_count(task_request: object | None) -> int:
    try:
        return max(0, int(getattr(task_request, "retries", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _resolve_retry_delay_seconds(
    retry_count: int,
    *,
    base_delay_sec: int = TASK_RETRY_DELAY_SECONDS,
    backoff_multiplier: float = TASK_RETRY_BACKOFF_MULTIPLIER,
    max_delay_sec: int = TASK_RETRY_MAX_DELAY_SECONDS,
) -> int:
    safe_base = max(0, int(base_delay_sec))
    safe_retry_count = max(0, int(retry_count))
    safe_multiplier = max(1.0, float(backoff_multiplier))
    calculated_delay = int(round(safe_base * (safe_multiplier ** safe_retry_count)))
    safe_max_delay = max(safe_base, int(max_delay_sec))
    return min(calculated_delay, safe_max_delay)


def _should_retry_task(
    *,
    retryable: bool,
    task_request: object | None,
    max_retries: int = TASK_MAX_RETRIES,
) -> bool:
    if not retryable or max_retries <= 0:
        return False
    if _task_called_directly(task_request):
        return False
    return _task_retry_count(task_request) < max_retries


@app.task(
    bind=True,
    name="process_vision_inference",
    soft_time_limit=TASK_SOFT_TIME_LIMIT_SECONDS,
    time_limit=TASK_TIME_LIMIT_SECONDS,
    max_retries=TASK_MAX_RETRIES,
    default_retry_delay=TASK_RETRY_DELAY_SECONDS,
)
def process_vision_inference(
    self,
    image_key,
    user_id,
    memory_id=None,
    captured_at=None,
    image_url=None,
    request_id=None,
    task_type="caption",
    enqueued_at=None,
):
    task_started_at = time.perf_counter()
    queue_wait_sec = _queue_wait_sec(enqueued_at)
    storage_read_sec = None
    image_decode_sec = None
    model_inference_sec = None
    model_key = "blip-base"
    quantization = "none"
    dtype_name = "float16"
    settings_source = "legacy_default"
    execution_policy_payload = None
    resolved_request_id = build_request_id(request_id)
    content_type = None
    model_mode = "unknown"
    model_id = "unknown"
    fallback_triggered = False

    try:
        execution_policy = resolve_runtime_execution_policy()
        settings = execution_policy.settings
        model_key = settings.model_key
        quantization = settings.quantization
        dtype_name = settings.dtype_name
        settings_source = settings.source
        execution_policy_payload = execution_policy.to_payload()
        model_descriptor = resolve_inference_model(model_key)
        model_mode = model_descriptor.mode
        model_id = model_descriptor.model_id
        storage_started_at = time.perf_counter()
        try:
            storage_object = get_storage_service().read_object(image_key)
        finally:
            storage_read_sec = _elapsed_sec(storage_started_at)
        content_type = storage_object.content_type
        image_data = storage_object.body
        image_decode_started_at = time.perf_counter()
        try:
            raw_image = Image.open(io.BytesIO(image_data)).convert("RGB")
        finally:
            image_decode_sec = _elapsed_sec(image_decode_started_at)

        model_inference_started_at = time.perf_counter()
        try:
            # If VISION_USE_OLLAMA=1, forward to Ollama adapter regardless of local model mode
            use_ollama = os.getenv("VISION_USE_OLLAMA", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
            if use_ollama:
                result = generate_ollama_vlm_metadata(
                    image=raw_image,
                    model_key=model_key,
                    quantization=quantization,
                    dtype_name=dtype_name,
                )
                metadata = result["metadata"]
                pipeline_output = result.get("pipeline_output")
            elif model_descriptor.mode == "vlm":
                try:
                    result = generate_qwen_vlm_metadata(
                        image=raw_image,
                        model_key=model_key,
                        quantization=quantization,
                        dtype_name=dtype_name,
                    )
                except Exception as primary_error:
                    fallback_model_key = None
                    if _should_retry_with_qwen_fallback(primary_error):
                        fallback_model_key = execution_policy.fallback_model_key
                    if fallback_model_key is None:
                        raise

                    logger.warning(
                        "Primary VLM inference failed, retrying with fallback model",
                        extra={
                            "task_name": "process_vision_inference",
                            "request_id": resolved_request_id,
                            "image_key": image_key,
                            "user_id": user_id,
                            "model_key": model_key,
                            "fallback_model_key": fallback_model_key,
                            "settings_source": settings_source,
                            "error_code": "vlm_primary_model_failed",
                        },
                    )
                    result = generate_qwen_vlm_metadata(
                        image=raw_image,
                        model_key=fallback_model_key,
                        quantization=quantization,
                        dtype_name=dtype_name,
                    )
                    model_key = fallback_model_key
                    model_descriptor = resolve_inference_model(model_key)
                    model_id = model_descriptor.model_id
                    fallback_triggered = True
                    execution_policy_payload = execution_policy.to_payload(
                        fallback_triggered=True
                    )
                metadata = result.get("metadata")
                pipeline_output = result.get("pipeline_output")
            else:
                result = generate_caption(
                    image=raw_image,
                    model_key=model_key,
                    quantization=quantization,
                    dtype_name=dtype_name,
                )
                metadata = None
                pipeline_output = None
        finally:
            model_inference_sec = _elapsed_sec(model_inference_started_at) # 광록님의 시간 측정 로직 살림!

        runtime_metrics = _build_task_runtime_metrics(
            task_started_at=task_started_at,
            queue_wait_sec=queue_wait_sec,
            storage_read_sec=storage_read_sec,
            image_decode_sec=image_decode_sec,
            model_inference_sec=model_inference_sec,
        )

        logger.info(
            "Inference task completed",
            extra={
                "task_name": "process_vision_inference",
                "request_id": resolved_request_id,
                "image_key": image_key,
                "memory_id": memory_id,
                "user_id": user_id,
                "model_key": model_key,
                "model_id": model_id,
                "model_mode": model_mode,
                "quantization": quantization,
                "dtype_name": dtype_name,
                "settings_source": settings_source,
                "soft_time_limit_sec": execution_policy.soft_time_limit_sec,
                "hard_time_limit_sec": execution_policy.hard_time_limit_sec,
                "fallback_model_key": execution_policy.fallback_model_key,
                "fallback_triggered": fallback_triggered,
                "latency_sec": round(result["elapsed_sec"], 4),
                "peak_memory_mb": result["peak_memory_mb"],
                **_log_runtime_metrics(runtime_metrics),
            },
        )

        return build_vlm_success_result(
            request_id=resolved_request_id,
            user_id=user_id,
            image_key=image_key,
            model_key=model_key,
            quantization=quantization,
            dtype_name=dtype_name,
            generation_result=result,
            memory_id=memory_id,
            image_url=image_url,
            captured_at=captured_at,
            task_type=task_type,
            content_type=content_type,
            inference_metadata=metadata,
            pipeline_output=pipeline_output,
            execution_policy=execution_policy_payload,
            runtime_metrics=runtime_metrics,
        )
    except Retry:
        raise
    except Exception as e:
        failure_policy = _classify_inference_error(e)
        error_details = _build_error_details(
            error=e,
            failure_policy=failure_policy,
        )
        task_request = getattr(self, "request", None)
        retry_count = _task_retry_count(task_request)
        runtime_metrics = _build_task_runtime_metrics(
            task_started_at=task_started_at,
            queue_wait_sec=queue_wait_sec,
            storage_read_sec=storage_read_sec,
            image_decode_sec=image_decode_sec,
            model_inference_sec=model_inference_sec,
        )

        retry_delay_sec = _resolve_retry_delay_seconds(retry_count)

        if _should_retry_task(retryable=failure_policy.retryable, task_request=task_request):
            logger.warning(
                "Inference task failed with retryable error, scheduling retry",
                extra={
                    "task_name": "process_vision_inference",
                    "request_id": resolved_request_id,
                    "image_key": image_key,
                    "memory_id": memory_id,
                    "user_id": user_id,
                    "model_key": model_key,
                    "model_id": model_id,
                    "model_mode": model_mode,
                    "quantization": quantization,
                    "dtype_name": dtype_name,
                    "settings_source": settings_source,
                    "error_code": failure_policy.error_code,
                    "retryable": failure_policy.retryable,
                    "failure_category": failure_policy.category,
                    "retry_count": retry_count,
                    "next_retry_count": retry_count + 1,
                    "max_retries": TASK_MAX_RETRIES,
                    "retry_delay_sec": retry_delay_sec,
                    "retry_backoff_multiplier": TASK_RETRY_BACKOFF_MULTIPLIER,
                    "retry_max_delay_sec": TASK_RETRY_MAX_DELAY_SECONDS,
                    **_log_runtime_metrics(runtime_metrics),
                },
            )
            raise self.retry(exc=e, countdown=retry_delay_sec)

        logger.exception(
            "Inference task failed",
            extra={
                "task_name": "process_vision_inference",
                "request_id": resolved_request_id,
                "image_key": image_key,
                "memory_id": memory_id,
                "user_id": user_id,
                "model_key": model_key,
                "model_id": model_id,
                "model_mode": model_mode,
                "quantization": quantization,
                "dtype_name": dtype_name,
                "settings_source": settings_source,
                "soft_time_limit_sec": TASK_SOFT_TIME_LIMIT_SECONDS,
                "hard_time_limit_sec": TASK_TIME_LIMIT_SECONDS,
                "error_code": failure_policy.error_code,
                "retryable": failure_policy.retryable,
                "failure_category": failure_policy.category,
                "retry_count": retry_count,
                "max_retries": TASK_MAX_RETRIES,
                **_log_runtime_metrics(runtime_metrics),
                "retry_delay_sec": retry_delay_sec,
                "retry_backoff_multiplier": TASK_RETRY_BACKOFF_MULTIPLIER,
                "retry_max_delay_sec": TASK_RETRY_MAX_DELAY_SECONDS,
            },
        )
        return build_vlm_error_result(
            request_id=resolved_request_id,
            user_id=user_id,
            image_key=image_key,
            error=e,
            model_key=model_key,
            quantization=quantization,
            dtype_name=dtype_name,
            memory_id=memory_id,
            image_url=image_url,
            captured_at=captured_at,
            task_type=task_type,
            content_type=content_type,
            error_code=failure_policy.error_code,
            retryable=failure_policy.retryable,
            execution_policy=execution_policy_payload,
            error_details=error_details,
            runtime_metrics=runtime_metrics,
        )
