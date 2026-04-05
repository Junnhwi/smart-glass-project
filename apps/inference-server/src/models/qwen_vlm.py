import math
import json
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import torch
from PIL import Image
from transformers import AutoProcessor, BitsAndBytesConfig

from src.contracts.qwen_parser import (
    build_metadata_tags,
    collect_nearby_candidate_names,
    deduplicate_object_names,
    extract_json_payload,
    merge_detected_object_candidates,
    normalize_qwen_metadata,
    normalize_structured_objects,
    object_names_from_structured_payload,
)


DEFAULT_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful assistant. Always respond in Korean. "
    "Return valid JSON only without markdown code fences."
)
DEFAULT_USER_PROMPT = """이미지를 보고 아래 JSON 형식으로만 응답하세요.

{
  "caption": "한 문장 요약",
  "sceneSummary": "장면 요약",
  "objects": [
    {"name": "물체명", "surface": "위치 단서", "nearby": ["주변 물체"]}
  ],
  "tags": ["검색용 태그"],
  "ocrText": null,
  "positionHint": "대표 위치 단서",
  "location": {
    "name": null,
    "address": null,
    "latitude": null,
    "longitude": null
  }
}
"""
OBJECT_REVIEW_PROMPT_TEMPLATE = """다음은 이미지에서 감지된 물체 후보 목록입니다.

{object_list}

규칙:
- 진짜 같은 물체를 가리키는 항목만 하나로 합칠 것
- 가장 구체적인 이름을 우선할 것
- 서로 다른 위치의 별도 물체라고 확신할 수 없으면 유지할 것
- 반드시 입력 목록에 있던 이름만 사용할 것
- JSON 배열만 출력

["물체1", "물체2", "..."]"""
MISSING_OBJECT_PROMPT_TEMPLATE = """현재 이미지에서 인식된 물체 목록입니다.

{object_list}

이미지를 다시 확인해서, 위 목록에 없는 중요한 물체가 있으면 추가한 전체 목록을 JSON 배열로 출력하세요.
- 책상 위 전자기기, 케이스, 태블릿, 스타일러스 펜, 이어폰, 지갑, 열쇠 같은 물체를 특히 확인하세요.
- 빠진 것이 확실하지 않으면 기존 목록을 그대로 유지하세요.
- 반드시 JSON 배열만 출력하세요.

["물체1", "물체2", "..."]"""


@dataclass(frozen=True)
class QwenVlmSpec:
    key: str
    model_id: str
    family: str = "qwen2_5_vl"
    recommended_quantization: str = "4bit"
    max_image_pixels: int = 1280 * 1280
    notes: str = ""


QWEN_MODEL_SPECS: Dict[str, QwenVlmSpec] = {
    "qwen2.5-vl-3b": QwenVlmSpec(
        key="qwen2.5-vl-3b",
        model_id="Qwen/Qwen2.5-VL-3B-Instruct",
        max_image_pixels=1280 * 1280,
        notes="smoke test와 빠른 구조 검증용 기본 VLM.",
    ),
    "qwen2.5-vl-7b": QwenVlmSpec(
        key="qwen2.5-vl-7b",
        model_id="Qwen/Qwen2.5-VL-7B-Instruct",
        max_image_pixels=1024 * 1024,
        notes="구조화된 JSON 응답 실험용 VLM 후보.",
    ),
}


def list_available_qwen_vlm_models() -> List[QwenVlmSpec]:
    return list(QWEN_MODEL_SPECS.values())


def get_qwen_vlm_spec(key: str) -> QwenVlmSpec:
    if key not in QWEN_MODEL_SPECS:
        raise KeyError(
            f"Unknown Qwen VLM model key: {key}. "
            f"Available keys: {', '.join(sorted(QWEN_MODEL_SPECS))}"
        )
    return QWEN_MODEL_SPECS[key]


def _resolve_dtype(dtype_name: str) -> torch.dtype:
    mapping = {
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "float32": torch.float32,
    }
    if dtype_name not in mapping:
        raise ValueError(
            f"Unsupported dtype: {dtype_name}. Choose one of {', '.join(mapping)}"
        )
    return mapping[dtype_name]


def _build_quantization_config(
    quantization: str, torch_dtype: torch.dtype
) -> Optional[BitsAndBytesConfig]:
    if quantization == "none":
        return None
    if quantization == "4bit":
        return BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch_dtype,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
    if quantization == "8bit":
        return BitsAndBytesConfig(load_in_8bit=True)
    raise ValueError(
        f"Unsupported quantization: {quantization}. Choose from none, 8bit, 4bit"
    )


def _require_qwen_dependencies() -> Any:
    try:
        from qwen_vl_utils import process_vision_info
    except Exception as exc:
        raise RuntimeError(
            "qwen-vl-utils is required for Qwen VLM inference. "
            "Install dependencies from apps/inference-server/requirements.txt."
        ) from exc
    return process_vision_info


def _resolve_max_image_pixels(spec: QwenVlmSpec) -> int:
    raw_value = os.getenv("VISION_QWEN_MAX_IMAGE_PIXELS", "").strip()
    if not raw_value:
        return spec.max_image_pixels
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(
            "VISION_QWEN_MAX_IMAGE_PIXELS must be an integer when set."
        ) from exc
    if value <= 0:
        raise ValueError("VISION_QWEN_MAX_IMAGE_PIXELS must be greater than 0.")
    return value


def _downscale_image_if_needed(image: Image.Image, max_image_pixels: int) -> Image.Image:
    width, height = image.size
    current_pixels = width * height
    if current_pixels <= max_image_pixels:
        return image

    scale = math.sqrt(max_image_pixels / float(current_pixels))
    resized_width = max(1, int(width * scale))
    resized_height = max(1, int(height * scale))
    return image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)


def _should_enable_object_review() -> bool:
    raw_value = os.getenv("VISION_QWEN_ENABLE_OBJECT_REVIEW", "").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _run_generation(
    *,
    model: Any,
    processor: Any,
    device_name: str,
    messages: List[Dict[str, Any]],
    process_vision_info: Any,
    max_new_tokens: int,
) -> str:
    prompt = processor.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    image_inputs, video_inputs = process_vision_info(messages)
    model_inputs = processor(
        text=[prompt],
        images=image_inputs,
        videos=video_inputs,
        return_tensors="pt",
    )
    model_inputs = model_inputs.to(device_name)

    with torch.inference_mode():
        output_ids = model.generate(
            **model_inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            repetition_penalty=1.2,
        )

    return processor.batch_decode(
        output_ids[:, model_inputs.input_ids.shape[1] :],
        skip_special_tokens=True,
    )[0]


def _review_object_candidates_with_vlm(
    *,
    image: Image.Image,
    candidate_names: List[str],
    model: Any,
    processor: Any,
    device_name: str,
    process_vision_info: Any,
) -> List[str]:
    clean_candidates = deduplicate_object_names(candidate_names)
    if len(clean_candidates) <= 1:
        return clean_candidates

    messages = [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {
                    "type": "text",
                    "text": OBJECT_REVIEW_PROMPT_TEMPLATE.format(
                        object_list=json.dumps(clean_candidates, ensure_ascii=False)
                    ),
                },
            ],
        },
    ]
    raw_text = _run_generation(
        model=model,
        processor=processor,
        device_name=device_name,
        messages=messages,
        process_vision_info=process_vision_info,
        max_new_tokens=256,
    )
    reviewed = deduplicate_object_names(
        extract_json_payload(raw_text, expect_array=True)
    )
    if not reviewed or len(reviewed) < max(1, len(clean_candidates) // 2):
        return clean_candidates
    return [name for name in reviewed if name in clean_candidates]


def _check_missing_objects_with_vlm(
    *,
    image: Image.Image,
    current_names: List[str],
    model: Any,
    processor: Any,
    device_name: str,
    process_vision_info: Any,
) -> List[str]:
    clean_candidates = deduplicate_object_names(current_names)
    if not clean_candidates:
        return []

    messages = [
        {"role": "system", "content": DEFAULT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {
                    "type": "text",
                    "text": MISSING_OBJECT_PROMPT_TEMPLATE.format(
                        object_list=json.dumps(clean_candidates, ensure_ascii=False)
                    ),
                },
            ],
        },
    ]
    raw_text = _run_generation(
        model=model,
        processor=processor,
        device_name=device_name,
        messages=messages,
        process_vision_info=process_vision_info,
        max_new_tokens=256,
    )
    updated = deduplicate_object_names(extract_json_payload(raw_text, expect_array=True))
    return [name for name in updated if name not in clean_candidates]


@lru_cache(maxsize=4)
def get_qwen_vlm_components(
    model_key: str,
    quantization: str = "4bit",
    device: str = DEFAULT_DEVICE,
    dtype_name: str = "float16",
) -> Tuple[str, QwenVlmSpec, Any, Any]:
    spec = get_qwen_vlm_spec(model_key)
    try:
        from transformers import Qwen2_5_VLForConditionalGeneration
    except ImportError as exc:
        raise RuntimeError(
            "Installed transformers version does not support Qwen2.5-VL."
        ) from exc

    torch_dtype = _resolve_dtype(dtype_name)
    quantization_config = _build_quantization_config(quantization, torch_dtype)
    kwargs: Dict[str, Any] = {
        "trust_remote_code": True,
    }
    if quantization_config is not None:
        kwargs["quantization_config"] = quantization_config
        kwargs["device_map"] = "auto"
    else:
        kwargs["torch_dtype"] = torch_dtype
        if device == "cuda":
            kwargs["device_map"] = "auto"

    started_at = time.perf_counter()
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(spec.model_id, **kwargs)
    processor = AutoProcessor.from_pretrained(
        spec.model_id,
        trust_remote_code=True,
        max_pixels=spec.max_image_pixels,
    )
    load_time_sec = time.perf_counter() - started_at
    setattr(model, "_load_time_sec", load_time_sec)
    model.eval()
    return device, spec, model, processor


def generate_qwen_vlm_metadata(
    image: Image.Image,
    model_key: str = "qwen2.5-vl-3b",
    quantization: str = "4bit",
    device: Optional[str] = None,
    dtype_name: str = "float16",
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    user_prompt: str = DEFAULT_USER_PROMPT,
    max_new_tokens: int = 512,
) -> Dict[str, Any]:
    process_vision_info = _require_qwen_dependencies()
    resolved_device = device or DEFAULT_DEVICE
    device_name, spec, model, processor = get_qwen_vlm_components(
        model_key=model_key,
        quantization=quantization,
        device=resolved_device,
        dtype_name=dtype_name,
    )
    resolved_image = _downscale_image_if_needed(
        image.convert("RGB"),
        max_image_pixels=_resolve_max_image_pixels(spec),
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": resolved_image},
                {"type": "text", "text": user_prompt},
            ],
        },
    ]

    if torch.cuda.is_available() and device_name.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()

    started_at = time.perf_counter()
    raw_text = _run_generation(
        model=model,
        processor=processor,
        device_name=device_name,
        messages=messages,
        process_vision_info=process_vision_info,
        max_new_tokens=max_new_tokens,
    )
    elapsed_sec = time.perf_counter() - started_at

    raw_payload = extract_json_payload(raw_text, expect_array=False)
    metadata = normalize_qwen_metadata(raw_payload)
    normalized_objects = normalize_structured_objects(raw_payload)
    merged_detected_objects = merge_detected_object_candidates(
        detected_objects=metadata["detectedObjects"]
        or object_names_from_structured_payload(raw_payload),
        structured_objects=normalized_objects,
    )

    if _should_enable_object_review():
        merged_detected_objects = _review_object_candidates_with_vlm(
            image=resolved_image,
            candidate_names=merged_detected_objects,
            model=model,
            processor=processor,
            device_name=device_name,
            process_vision_info=process_vision_info,
        )
        merged_detected_objects = deduplicate_object_names(
            merged_detected_objects
            + collect_nearby_candidate_names(normalized_objects, merged_detected_objects)
            + _check_missing_objects_with_vlm(
                image=resolved_image,
                current_names=merged_detected_objects,
                model=model,
                processor=processor,
                device_name=device_name,
                process_vision_info=process_vision_info,
            )
        )

    metadata["detectedObjects"] = merged_detected_objects
    metadata["tags"] = build_metadata_tags(metadata, normalized_objects)

    peak_memory_mb = 0.0
    if torch.cuda.is_available() and device_name.startswith("cuda"):
        peak_memory_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)

    return {
        "metadata": metadata,
        "elapsed_sec": round(elapsed_sec, 4),
        "peak_memory_mb": round(peak_memory_mb, 2),
        "load_time_sec": round(getattr(model, "_load_time_sec", 0.0), 4),
        "model_id": spec.model_id,
        "model_key": spec.key,
        "device": device_name,
        "quantization": quantization,
        "prompt": user_prompt,
        "system_prompt": system_prompt,
        "raw_output_text": raw_text,
    }
