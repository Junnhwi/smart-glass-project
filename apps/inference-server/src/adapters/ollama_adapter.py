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

VLM_METADATA_PROMPT = """You are a helpful assistant. Always respond in Korean. Output valid JSON only. No code blocks.

이미지를 분석하여 다음 JSON 형식으로 출력하세요. 설명 없이 JSON만 출력하세요.

{
  "caption": "사진 전체에 대한 한 문장 설명",
  "sceneSummary": "전체 장면 10단어 이내 요약",
  "location": "공간 유형 (예: 거실, 카페, 사무실)",
  "detectedObjects": ["물체1", "물체2"],
  "objects": [
    {
      "name": "물체명 (가장 구체적인 이름)",
      "positionHint": "주변 물체 기준 상대적 위치 (예: 맥북 오른쪽, 아이폰 아래)",
      "surface": "놓인 표면 또는 기준 물체. 예: 맥북 위, 테이블 위 왼쪽. 절대 비워두지 말 것",
      "nearbyObjects": ["주변 물체1", "주변 물체2"]
    }
  ],
  "tags": ["검색용 태그 키워드들"],
  "ocrText": "보이는 텍스트가 있다면 기록, 없으면 null",
  "positionHint": "가장 찾기 쉬운 메인 물체의 종합적 위치 단서"
}

규칙:
- 작거나 부분만 보여도 포함
- 브랜드 제품은 브랜드명 포함 (예: AirPods, 맥북, 아이패드, Apple Pencil)
- 태블릿/스마트패드/아이패드도 반드시 포함
- 같은 종류가 여러 개면 모두 포함 (예: AirPods 케이스가 2개면 "AirPods 케이스 1", "AirPods 케이스 2")
- 가구/벽/바닥 제외
- JSON만 출력
- 반드시 한국어로""".strip()


def _image_to_base64_jpeg(image: Image.Image) -> str:
    # 640x480으로 리사이징 (VLM 입력 고정)
    resized = image.resize((640, 480), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    resized.save(buf, format="JPEG", quality=85)
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
