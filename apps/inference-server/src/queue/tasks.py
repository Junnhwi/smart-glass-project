import os
import io
from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded
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
from src.models.registry import resolve_inference_model
from src.models.serving_profile import resolve_runtime_serving_settings
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


def _resolve_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


TASK_SOFT_TIME_LIMIT_SECONDS = _resolve_positive_int_env(
    "VISION_TASK_SOFT_TIME_LIMIT_SEC",
    120,
)
TASK_TIME_LIMIT_SECONDS = max(
    _resolve_positive_int_env("VISION_TASK_HARD_TIME_LIMIT_SEC", 150),
    TASK_SOFT_TIME_LIMIT_SECONDS + 1,
)

app.conf.update(
    task_track_started=True,
    result_expires=3600,
    task_soft_time_limit=TASK_SOFT_TIME_LIMIT_SECONDS,
    task_time_limit=TASK_TIME_LIMIT_SECONDS,
)
configure_logging()
logger = get_logger(__name__)


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


def _resolve_qwen_fallback_model(current_model_key: str) -> str | None:
    fallback_model_key = (
        os.getenv("VISION_QWEN_FALLBACK_MODEL", "qwen2.5-vl-3b").strip()
        or "qwen2.5-vl-3b"
    )
    if fallback_model_key == current_model_key:
        return None
    try:
        descriptor = resolve_inference_model(fallback_model_key)
    except Exception:
        return None
    if descriptor.mode != "vlm":
        return None
    return descriptor.key


def _classify_inference_error(error: Exception) -> tuple[str, bool]:
    if isinstance(error, (SoftTimeLimitExceeded, TimeoutError)):
        return "inference_timeout", True
    if isinstance(error, StorageNotFoundError):
        return "source_image_not_found", False
    if isinstance(error, StorageConfigError):
        return "storage_config_error", False
    if isinstance(error, StorageAccessError):
        return "storage_access_error", True
    if isinstance(error, UnidentifiedImageError):
        return "invalid_source_image", False
    if isinstance(error, ValueError):
        return "invalid_inference_request", False
    if isinstance(error, RuntimeError):
        return "model_runtime_error", True
    return "inference_task_error", True


@app.task(
    name="process_vision_inference",
    soft_time_limit=TASK_SOFT_TIME_LIMIT_SECONDS,
    time_limit=TASK_TIME_LIMIT_SECONDS,
)
def process_vision_inference(
    image_key,
    user_id,
    memory_id=None,
    captured_at=None,
    image_url=None,
    request_id=None,
    task_type="caption",
):
    model_key = "blip-base"
    quantization = "none"
    dtype_name = "float16"
    settings_source = "legacy_default"
    resolved_request_id = build_request_id(request_id)
    content_type = None
    model_mode = "unknown"

    try:
        settings = resolve_runtime_serving_settings()
        model_key = settings.model_key
        quantization = settings.quantization
        dtype_name = settings.dtype_name
        settings_source = settings.source
        model_descriptor = resolve_inference_model(model_key)
        model_mode = model_descriptor.mode
        storage_object = get_storage_service().read_object(image_key)
        content_type = storage_object.content_type
        image_data = storage_object.body
        raw_image = Image.open(io.BytesIO(image_data)).convert("RGB")
        if model_descriptor.mode == "vlm":
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
                    fallback_model_key = _resolve_qwen_fallback_model(model_key)
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
            metadata = result["metadata"]
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

        logger.info(
            "Inference task completed",
            extra={
                "task_name": "process_vision_inference",
                "request_id": resolved_request_id,
                "image_key": image_key,
                "memory_id": memory_id,
                "user_id": user_id,
                "model_key": model_key,
                "model_mode": model_mode,
                "quantization": quantization,
                "settings_source": settings_source,
                "latency_sec": round(result["elapsed_sec"], 4),
                "peak_memory_mb": result["peak_memory_mb"],
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
        )
    except Exception as e:
        error_code, retryable = _classify_inference_error(e)
        logger.exception(
            "Inference task failed",
            extra={
                "task_name": "process_vision_inference",
                "request_id": resolved_request_id,
                "image_key": image_key,
                "memory_id": memory_id,
                "user_id": user_id,
                "model_key": model_key,
                "model_mode": model_mode,
                "quantization": quantization,
                "settings_source": settings_source,
                "error_code": error_code,
                "retryable": retryable,
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
            error_code=error_code,
            retryable=retryable,
        )
