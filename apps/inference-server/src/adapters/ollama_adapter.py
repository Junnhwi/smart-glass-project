import base64
import io
import time
import logging
from typing import Any, Dict, Optional

from PIL import Image

from src.clients.ollama_client import make_ollama_client
from src.contracts.vlm import build_vlm_error_result, build_vlm_success_result

logger = logging.getLogger(__name__)


def _image_to_base64_jpeg(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def generate_ollama_vlm_metadata(
    *,
    image: Image.Image,
    model_key: str = "ollama-vl",
    quantization: str = "none",
    dtype_name: str = "float16",
) -> Dict[str, Any]:
    client = make_ollama_client()
    b64 = _image_to_base64_jpeg(image)
    payload = {
        "task": "vlm_metadata",
        "image_base64": b64,
        "options": {"model_key": model_key, "quantization": quantization},
    }

    started = time.perf_counter()
    try:
        resp = client.send_vlm_input(payload)
    except Exception as e:
        logger.exception("Ollama adapter failed: %s", e)
        raise
    elapsed = time.perf_counter() - started

    # Basic mapping: expect resp to contain caption, detectedObjects
    caption = resp.get("caption") or resp.get("summary") or None
    detected = resp.get("detectedObjects") or resp.get("objects") or []
    metadata = {
        "caption": caption,
        "sceneSummary": caption,
        "detectedObjects": detected,
        "tags": resp.get("tags") or [],
        "ocrText": resp.get("ocrText") or None,
        "positionHint": resp.get("positionHint") or None,
        "location": resp.get("location") or None,
    }

    pipeline_output = {
        "capture_id": f"ollama-{int(started*1000)}",
        "timestamp": resp.get("timestamp"),
        "objects": resp.get("objects_details") or [],
        "inference_time": round(elapsed, 3),
    }

    return {
        "metadata": metadata,
        "elapsed_sec": round(elapsed, 4),
        "peak_memory_mb": 0.0,
        "load_time_sec": 0.0,
        "model_id": model_key,
        "model_key": model_key,
        "device": "external-ollama",
        "quantization": quantization,
        "prompt": None,
        "system_prompt": None,
        "raw_output_text": resp.get("raw") or None,
        "objects": resp.get("objects") or [],
        "scene_info": {"summary": caption},
        "pipeline_output": pipeline_output,
        "pipeline_mode": "ollama_adapter",
    }
