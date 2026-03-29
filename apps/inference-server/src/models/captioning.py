import os
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import torch
from PIL import Image
from transformers import (
    AutoProcessor,
    AutoTokenizer,
    BitsAndBytesConfig,
    BlipForConditionalGeneration,
    BlipProcessor,
    GitForCausalLM,
    VisionEncoderDecoderModel,
    ViTImageProcessor,
)


DEFAULT_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


@dataclass(frozen=True)
class CaptionModelSpec:
    key: str
    model_id: str
    family: str
    default_prompt: Optional[str] = None
    recommended_quantization: str = "none"
    notes: str = ""


MODEL_SPECS: Dict[str, CaptionModelSpec] = {
    "blip-base": CaptionModelSpec(
        key="blip-base",
        model_id="Salesforce/blip-image-captioning-base",
        family="blip",
        default_prompt="a photography of",
        notes="빠른 베이스라인. 첫 비교 대상으로 적합합니다.",
    ),
    "blip-large": CaptionModelSpec(
        key="blip-large",
        model_id="Salesforce/blip-image-captioning-large",
        family="blip",
        default_prompt="a photography of",
        notes="정확도 향상을 기대할 수 있지만 메모리 사용량이 늘어납니다.",
    ),
    "git-base": CaptionModelSpec(
        key="git-base",
        model_id="microsoft/git-base-coco",
        family="git",
        notes="상대적으로 가벼운 캡셔닝 전용 모델입니다.",
    ),
    "vit-gpt2": CaptionModelSpec(
        key="vit-gpt2",
        model_id="nlpconnect/vit-gpt2-image-captioning",
        family="vit-gpt2",
        notes="구현이 단순하고 CPU fallback 테스트에도 유용합니다.",
    ),
    "blip2-opt-2.7b": CaptionModelSpec(
        key="blip2-opt-2.7b",
        model_id="Salesforce/blip2-opt-2.7b",
        family="blip2",
        recommended_quantization="4bit",
        notes="RTX 4070에서는 4-bit 또는 8-bit 양자화 권장.",
    ),
}


def list_available_caption_models() -> List[CaptionModelSpec]:
    return list(MODEL_SPECS.values())


def get_caption_model_spec(key: str) -> CaptionModelSpec:
    if key not in MODEL_SPECS:
        raise KeyError(
            f"Unknown model key: {key}. Available keys: {', '.join(sorted(MODEL_SPECS))}"
        )
    return MODEL_SPECS[key]


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
    if quantization == "8bit":
        return BitsAndBytesConfig(load_in_8bit=True)
    if quantization == "4bit":
        return BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch_dtype,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
    raise ValueError(
        f"Unsupported quantization: {quantization}. Choose from none, 8bit, 4bit"
    )


def _base_model_kwargs(
    device: str, quantization: str, dtype_name: str
) -> Dict[str, Any]:
    torch_dtype = _resolve_dtype(dtype_name)
    kwargs: Dict[str, Any] = {}
    quantization_config = _build_quantization_config(quantization, torch_dtype)

    if quantization_config is not None:
        kwargs["quantization_config"] = quantization_config
        kwargs["device_map"] = "auto"
    else:
        if device == "cuda":
            kwargs["torch_dtype"] = torch_dtype

    return kwargs


def _load_blip(
    spec: CaptionModelSpec, device: str, quantization: str, dtype_name: str
) -> Tuple[Any, Any]:
    processor = BlipProcessor.from_pretrained(spec.model_id)
    kwargs = _base_model_kwargs(device, quantization, dtype_name)
    model = BlipForConditionalGeneration.from_pretrained(spec.model_id, **kwargs)
    if quantization == "none":
        model = model.to(device)
    model.eval()
    return model, processor


def _load_git(
    spec: CaptionModelSpec, device: str, quantization: str, dtype_name: str
) -> Tuple[Any, Any]:
    processor = AutoProcessor.from_pretrained(spec.model_id)
    kwargs = _base_model_kwargs(device, quantization, dtype_name)
    model = GitForCausalLM.from_pretrained(spec.model_id, **kwargs)
    if quantization == "none":
        model = model.to(device)
    model.eval()
    return model, processor


def _load_vit_gpt2(
    spec: CaptionModelSpec, device: str, quantization: str, dtype_name: str
) -> Tuple[Any, Any]:
    feature_extractor = ViTImageProcessor.from_pretrained(spec.model_id)
    tokenizer = AutoTokenizer.from_pretrained(spec.model_id)
    kwargs = _base_model_kwargs(device, quantization, dtype_name)
    model = VisionEncoderDecoderModel.from_pretrained(spec.model_id, **kwargs)
    if quantization == "none":
        model = model.to(device)
    model.eval()
    processor = {"feature_extractor": feature_extractor, "tokenizer": tokenizer}
    return model, processor


def _load_blip2(
    spec: CaptionModelSpec, device: str, quantization: str, dtype_name: str
) -> Tuple[Any, Any]:
    try:
        from transformers import AutoModelForVision2Seq

        model_class = AutoModelForVision2Seq
    except ImportError:
        from transformers import Blip2ForConditionalGeneration

        model_class = Blip2ForConditionalGeneration

    processor = AutoProcessor.from_pretrained(spec.model_id)
    kwargs = _base_model_kwargs(device, quantization, dtype_name)
    model = model_class.from_pretrained(spec.model_id, **kwargs)
    if quantization == "none":
        model = model.to(device)
    model.eval()
    return model, processor


MODEL_LOADERS = {
    "blip": _load_blip,
    "git": _load_git,
    "vit-gpt2": _load_vit_gpt2,
    "blip2": _load_blip2,
}


@lru_cache(maxsize=8)
def get_caption_model_components(
    model_key: str,
    quantization: str = "none",
    device: str = DEFAULT_DEVICE,
    dtype_name: str = "float16",
) -> Tuple[str, CaptionModelSpec, Any, Any]:
    spec = get_caption_model_spec(model_key)
    if spec.family not in MODEL_LOADERS:
        raise ValueError(f"Unsupported model family: {spec.family}")

    started_at = time.perf_counter()
    model, processor = MODEL_LOADERS[spec.family](spec, device, quantization, dtype_name)
    load_time_sec = time.perf_counter() - started_at
    setattr(model, "_load_time_sec", load_time_sec)

    return device, spec, model, processor


def _move_inputs_to_device(inputs: Dict[str, Any], device: str) -> Dict[str, Any]:
    moved: Dict[str, Any] = {}
    for key, value in inputs.items():
        if hasattr(value, "to"):
            moved[key] = value.to(device)
        else:
            moved[key] = value
    return moved


def generate_caption(
    image: Image.Image,
    model_key: str = "blip-base",
    quantization: str = "none",
    device: Optional[str] = None,
    dtype_name: str = "float16",
    prompt: Optional[str] = None,
    max_new_tokens: int = 32,
    num_beams: int = 3,
) -> Dict[str, Any]:
    resolved_device = device or DEFAULT_DEVICE
    resolved_image = image.convert("RGB")
    device_name, spec, model, processor = get_caption_model_components(
        model_key=model_key,
        quantization=quantization,
        device=resolved_device,
        dtype_name=dtype_name,
    )
    effective_prompt = prompt if prompt is not None else spec.default_prompt

    if torch.cuda.is_available() and resolved_device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()
    started_at = time.perf_counter()

    with torch.inference_mode():
        if spec.family == "vit-gpt2":
            feature_extractor = processor["feature_extractor"]
            tokenizer = processor["tokenizer"]
            pixel_values = feature_extractor(
                images=resolved_image, return_tensors="pt"
            ).pixel_values
            pixel_values = pixel_values.to(device_name)
            output_ids = model.generate(
                pixel_values,
                max_new_tokens=max_new_tokens,
                num_beams=num_beams,
            )
            caption = tokenizer.decode(output_ids[0], skip_special_tokens=True).strip()
        else:
            processor_kwargs: Dict[str, Any] = {
                "images": resolved_image,
                "return_tensors": "pt",
            }
            if effective_prompt:
                processor_kwargs["text"] = effective_prompt
            model_inputs = processor(**processor_kwargs)
            model_inputs = _move_inputs_to_device(model_inputs, device_name)
            output_ids = model.generate(
                **model_inputs,
                max_new_tokens=max_new_tokens,
                num_beams=num_beams,
            )
            caption = processor.decode(output_ids[0], skip_special_tokens=True).strip()

    elapsed_sec = time.perf_counter() - started_at
    peak_memory_mb = 0.0
    if torch.cuda.is_available() and device_name.startswith("cuda"):
        peak_memory_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)

    return {
        "caption": caption,
        "elapsed_sec": elapsed_sec,
        "peak_memory_mb": round(peak_memory_mb, 2),
        "load_time_sec": round(getattr(model, "_load_time_sec", 0.0), 4),
        "model_id": spec.model_id,
        "model_key": spec.key,
        "device": device_name,
        "quantization": quantization,
        "prompt": effective_prompt,
    }


def open_image(image_path: str) -> Image.Image:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")
    return Image.open(image_path).convert("RGB")
