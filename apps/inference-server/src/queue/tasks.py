import os
import io
from celery import Celery
from PIL import Image

from src.contracts.vlm import (
    build_request_id,
    build_vlm_error_result,
    build_vlm_success_result,
)
from src.core.logging import configure_logging, get_logger
from src.models.captioning import generate_caption
from src.models.qwen_vlm import generate_qwen_vlm_metadata
from src.models.registry import resolve_inference_model
from src.storage.s3 import get_s3_client

broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
app = Celery("inference_tasks", broker=broker_url)
configure_logging()
logger = get_logger(__name__)


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


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


@app.task(name="process_vision_inference")
def process_vision_inference(
    image_key,
    user_id,
    memory_id=None,
    captured_at=None,
    image_url=None,
    request_id=None,
    task_type="caption",
):
    bucket_name = _require_env("AWS_S3_BUCKET_NAME")
    model_key = os.getenv("VISION_CAPTION_MODEL", "blip-base").strip() or "blip-base"
    quantization = (
        os.getenv("VISION_CAPTION_QUANTIZATION", "none").strip() or "none"
    )
    dtype_name = os.getenv("VISION_CAPTION_DTYPE", "float16").strip() or "float16"
    resolved_request_id = build_request_id(request_id)
    content_type = None
    model_mode = "unknown"

    try:
        model_descriptor = resolve_inference_model(model_key)
        model_mode = model_descriptor.mode
        s3_client = get_s3_client()
        response = s3_client.get_object(Bucket=bucket_name, Key=image_key)
        content_type = response.get("ContentType")
        image_data = response["Body"].read()
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
                "error_code": "inference_task_error",
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
            task_type=task_type,
            content_type=content_type,
        )
