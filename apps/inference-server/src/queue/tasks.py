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

    try:
        s3_client = get_s3_client()
        response = s3_client.get_object(Bucket=bucket_name, Key=image_key)
        content_type = response.get("ContentType")
        image_data = response["Body"].read()
        raw_image = Image.open(io.BytesIO(image_data)).convert("RGB")
        result = generate_caption(
            image=raw_image,
            model_key=model_key,
            quantization=quantization,
            dtype_name=dtype_name,
        )
        caption = result["caption"]

        logger.info(
            "Inference task completed",
            extra={
                "task_name": "process_vision_inference",
                "request_id": resolved_request_id,
                "image_key": image_key,
                "memory_id": memory_id,
                "user_id": user_id,
                "model_key": model_key,
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
