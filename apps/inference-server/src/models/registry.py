from dataclasses import dataclass

from src.models.captioning import get_caption_model_spec
from src.models.qwen_vlm import get_qwen_vlm_spec


@dataclass(frozen=True)
class InferenceModelDescriptor:
    key: str
    model_id: str
    family: str
    mode: str
    recommended_quantization: str
    notes: str


def resolve_inference_model(model_key: str) -> InferenceModelDescriptor:
    try:
        spec = get_caption_model_spec(model_key)
        return InferenceModelDescriptor(
            key=spec.key,
            model_id=spec.model_id,
            family=spec.family,
            mode="caption",
            recommended_quantization=spec.recommended_quantization,
            notes=spec.notes,
        )
    except Exception:
        pass

    spec = get_qwen_vlm_spec(model_key)
    return InferenceModelDescriptor(
        key=spec.key,
        model_id=spec.model_id,
        family=spec.family,
        mode="vlm",
        recommended_quantization=spec.recommended_quantization,
        notes=spec.notes,
    )
