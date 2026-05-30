from dataclasses import dataclass

@dataclass(frozen=True)
class InferenceModelCapabilities:
    caption: bool
    position_hint: bool
    scene_summary: bool
    detected_objects: bool
    tags: bool
    ocr_text: bool
    location: bool
    pipeline_output: bool

    def to_contract_payload(self) -> dict[str, bool]:
        return {
            "caption": self.caption,
            "positionHint": self.position_hint,
            "sceneSummary": self.scene_summary,
            "detectedObjects": self.detected_objects,
            "tags": self.tags,
            "ocrText": self.ocr_text,
            "location": self.location,
            "pipelineOutput": self.pipeline_output,
        }


@dataclass(frozen=True)
class InferenceModelDescriptor:
    key: str
    model_id: str
    family: str
    mode: str
    recommended_quantization: str
    notes: str
    capabilities: InferenceModelCapabilities


CAPTION_CAPABILITIES = InferenceModelCapabilities(
    caption=True,
    position_hint=True,
    scene_summary=False,
    detected_objects=False,
    tags=False,
    ocr_text=False,
    location=False,
    pipeline_output=False,
)

QWEN_VLM_CAPABILITIES = InferenceModelCapabilities(
    caption=True,
    position_hint=True,
    scene_summary=True,
    detected_objects=True,
    tags=True,
    ocr_text=False,
    location=False,
    pipeline_output=True,
)

MODEL_DESCRIPTORS = {
    "blip-base": InferenceModelDescriptor(
        key="blip-base",
        model_id="Salesforce/blip-image-captioning-base",
        family="blip",
        mode="caption",
        recommended_quantization="none",
        notes="빠른 베이스라인. 첫 비교 대상으로 적합합니다.",
        capabilities=CAPTION_CAPABILITIES,
    ),
    "blip-large": InferenceModelDescriptor(
        key="blip-large",
        model_id="Salesforce/blip-image-captioning-large",
        family="blip",
        mode="caption",
        recommended_quantization="none",
        notes="정확도 향상을 기대할 수 있지만 메모리 사용량이 늘어납니다.",
        capabilities=CAPTION_CAPABILITIES,
    ),
    "git-base": InferenceModelDescriptor(
        key="git-base",
        model_id="microsoft/git-base-coco",
        family="git",
        mode="caption",
        recommended_quantization="none",
        notes="상대적으로 가벼운 캡셔닝 전용 모델입니다.",
        capabilities=CAPTION_CAPABILITIES,
    ),
    "vit-gpt2": InferenceModelDescriptor(
        key="vit-gpt2",
        model_id="nlpconnect/vit-gpt2-image-captioning",
        family="vit-gpt2",
        mode="caption",
        recommended_quantization="none",
        notes="구현이 단순하고 CPU fallback 테스트에도 유용합니다.",
        capabilities=CAPTION_CAPABILITIES,
    ),
    "blip2-opt-2.7b": InferenceModelDescriptor(
        key="blip2-opt-2.7b",
        model_id="Salesforce/blip2-opt-2.7b",
        family="blip2",
        mode="caption",
        recommended_quantization="4bit",
        notes="RTX 4070에서는 4-bit 또는 8-bit 양자화 권장.",
        capabilities=CAPTION_CAPABILITIES,
    ),
    "qwen2.5-vl-3b": InferenceModelDescriptor(
        key="qwen2.5-vl-3b",
        model_id="Qwen/Qwen2.5-VL-3B-Instruct",
        family="qwen2_5_vl",
        mode="vlm",
        recommended_quantization="4bit",
        notes="smoke test와 빠른 구조 검증용 기본 VLM.",
        capabilities=QWEN_VLM_CAPABILITIES,
    ),
    "qwen2.5-vl-7b": InferenceModelDescriptor(
        key="qwen2.5-vl-7b",
        model_id="Qwen/Qwen2.5-VL-7B-Instruct",
        family="qwen2_5_vl",
        mode="vlm",
        recommended_quantization="4bit",
        notes="구조화된 JSON 응답 실험용 VLM 후보.",
        capabilities=QWEN_VLM_CAPABILITIES,
    ),
}


def resolve_inference_model(model_key: str) -> InferenceModelDescriptor:
    try:
        return MODEL_DESCRIPTORS[model_key]
    except KeyError as exc:
        raise KeyError(
            f"Unknown inference model key: {model_key}. "
            f"Available keys: {', '.join(sorted(MODEL_DESCRIPTORS))}"
        ) from exc
