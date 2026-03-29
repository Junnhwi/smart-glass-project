import os

from src.models.captioning import get_caption_model_components


def get_blip_components():
    model_key = os.getenv("VISION_CAPTION_MODEL", "blip-base").strip() or "blip-base"
    quantization = os.getenv("VISION_CAPTION_QUANTIZATION", "none").strip() or "none"
    dtype_name = os.getenv("VISION_CAPTION_DTYPE", "float16").strip() or "float16"
    device, _, model, processor = get_caption_model_components(
        model_key=model_key,
        quantization=quantization,
        dtype_name=dtype_name,
    )
    return device, model, processor
