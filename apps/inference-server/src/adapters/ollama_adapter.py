import base64
import io
import time
import logging
from typing import Any, Dict, Optional

from PIL import Image

from src.clients.ollama_client import make_ollama_client
from src.contracts.qwen_parser import extract_json_payload
from src.contracts.vlm import build_vlm_error_result, build_vlm_success_result

logger = logging.getLogger(__name__)

VLM_METADATA_PROMPT = """
Analyze this smart-glass image for searchable memory retrieval.
Return only a JSON object with these fields:
{
  "caption": "short natural-language image caption",
  "sceneSummary": "short scene summary",
  "detectedObjects": ["object names visible in the image"],
  "objects": [
    {
      "name": "object name",
      "positionHint": "where it is, using nearby objects or surfaces",
      "nearbyObjects": ["nearby object names"],
      "surface": "desk/table/floor/shelf/etc or null"
    }
  ],
  "tags": ["search tags"],
  "ocrText": "visible text if any, otherwise null",
  "positionHint": "best overall location hint for the most findable object",
  "location": null
}
For each important object, describe its location relative to stable anchors.
Prefer concrete hints like "AirPods on the laptop at the lower right" or
"phone near the center-bottom of the desk". Do not invent hidden objects.
Use concise object names. Do not include markdown.
""".strip()


def _image_to_base64_jpeg(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        cleaned = " ".join(str(item).split())
        if not cleaned or cleaned in seen:
            continue
        normalized.append(cleaned)
        seen.add(cleaned)
    return normalized


def _normalize_optional_text(value: Any) -> str | None:
    cleaned = " ".join(str(value or "").split())
    return cleaned or None


def _normalize_ollama_objects(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value, start=1):
        if isinstance(item, str):
            name = _normalize_optional_text(item)
            position_hint = None
            nearby_objects: list[str] = []
            surface = None
        elif isinstance(item, dict):
            name = _normalize_optional_text(item.get("name"))
            position_hint = _normalize_optional_text(
                item.get("positionHint")
                or item.get("position_hint")
                or item.get("location")
                or item.get("spatialHint")
            )
            nearby_objects = _normalize_string_list(
                item.get("nearbyObjects")
                or item.get("nearby_objects")
                or item.get("nearby")
            )
            surface = _normalize_optional_text(item.get("surface"))
        else:
            continue

        if not name:
            continue
        lowered = name.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(
            {
                "object_id": len(normalized) + 1,
                "name": name,
                "position": {
                    "hint": position_hint,
                    "surface": surface,
                },
                "nearby_objects": nearby_objects,
            }
        )

    return normalized


def _choose_position_hint(
    *,
    parsed_position_hint: Any,
    objects: list[dict[str, Any]],
    caption: str | None,
) -> str | None:
    explicit = _normalize_optional_text(parsed_position_hint)
    if explicit:
        return explicit
    for item in objects:
        hint = _normalize_optional_text((item.get("position") or {}).get("hint"))
        if hint:
            return hint
    return caption


def _parse_ollama_chat_metadata(response: Dict[str, Any]) -> Dict[str, Any]:
    content = ""
    message = response.get("message")
    if isinstance(message, dict):
        content = str(message.get("content") or "")
    if not content:
        content = str(response.get("response") or response.get("content") or "")

    parsed = extract_json_payload(content)
    if not isinstance(parsed, dict):
        parsed = {}

    caption = (
        " ".join(str(parsed.get("caption") or parsed.get("summary") or "").split())
        or None
    )
    scene_summary = (
        " ".join(str(parsed.get("sceneSummary") or parsed.get("scene_summary") or "").split())
        or caption
    )
    detected = _normalize_string_list(
        parsed.get("detectedObjects")
        or parsed.get("detected_objects")
        or parsed.get("objects")
    )
    objects = _normalize_ollama_objects(
        parsed.get("objects")
        or parsed.get("objectLocations")
        or parsed.get("object_locations")
    )
    if not detected and objects:
        detected = [item["name"] for item in objects]
    tags = _normalize_string_list(parsed.get("tags"))
    position_hint = _choose_position_hint(
        parsed_position_hint=parsed.get("positionHint")
        or parsed.get("position_hint"),
        objects=objects,
        caption=caption,
    )

    return {
        "caption": caption,
        "sceneSummary": scene_summary,
        "detectedObjects": detected,
        "objects": objects,
        "tags": tags,
        "ocrText": parsed.get("ocrText") or parsed.get("ocr_text") or None,
        "positionHint": position_hint,
        "location": parsed.get("location") or None,
        "_raw_content": content,
    }


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
        "messages": [
            {
                "role": "user",
                "content": VLM_METADATA_PROMPT,
                "images": [b64],
            }
        ],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0},
    }

    started = time.perf_counter()
    try:
        resp = client.send_vlm_input(payload)
    except Exception as e:
        logger.exception("Ollama adapter failed: %s", e)
        raise
    elapsed = time.perf_counter() - started

    parsed_metadata = _parse_ollama_chat_metadata(resp)
    caption = parsed_metadata["caption"]
    detected = parsed_metadata["detectedObjects"]
    objects = parsed_metadata["objects"]
    metadata = {
        "caption": caption,
        "sceneSummary": parsed_metadata["sceneSummary"],
        "detectedObjects": detected,
        "tags": parsed_metadata["tags"],
        "ocrText": parsed_metadata["ocrText"],
        "positionHint": parsed_metadata["positionHint"],
        "location": parsed_metadata["location"],
    }

    pipeline_output = {
        "capture_id": f"ollama-{int(started*1000)}",
        "timestamp": resp.get("created_at"),
        "objects": objects or [{"name": name} for name in detected],
        "inference_time": round(elapsed, 3),
        "done_reason": resp.get("done_reason"),
    }

    return {
        "metadata": metadata,
        "elapsed_sec": round(elapsed, 4),
        "peak_memory_mb": 0.0,
        "load_time_sec": 0.0,
        "provider": "ollama",
        "model_id": resp.get("model") or client.vlm_model,
        "model_key": resp.get("model") or client.vlm_model,
        "device": "external-ollama",
        "quantization": quantization,
        "prompt": VLM_METADATA_PROMPT,
        "system_prompt": None,
        "raw_output_text": parsed_metadata["_raw_content"] or None,
        "objects": objects or [{"name": name} for name in detected],
        "scene_info": {"summary": caption},
        "pipeline_output": pipeline_output,
        "pipeline_mode": "ollama_adapter",
    }
