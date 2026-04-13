from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, validator


class ApiSchema(BaseModel):
    class Config:
        extra = "ignore"
        anystr_strip_whitespace = True
        allow_population_by_field_name = True


class CaptureSourceImagePayload(ApiSchema):
    imageKey: str | None = None
    imageUrl: str | None = None
    contentType: str | None = None


class GenerationConfigPayload(ApiSchema):
    modelKey: str | None = None
    quantization: Literal["none", "8bit", "4bit"] | None = None
    dtype: Literal["float16", "bfloat16", "float32"] | None = None
    prompt: str | None = None
    maxNewTokens: int | None = Field(default=None, ge=1)
    numBeams: int | None = Field(default=None, ge=1)


class CaptureUploadRequest(ApiSchema):

    captureId: str | None = None
    requestId: str | None = None
    memoryId: str | None = None
    userId: str = Field(min_length=1)
    taskType: Literal["caption", "metadata"] = "metadata"
    capturedAt: str | None = None
    fileName: str | None = None
    imageKey: str | None = None
    imageUrl: str | None = None
    contentType: str | None = None
    sourceImage: CaptureSourceImagePayload | None = None
    generation: GenerationConfigPayload | None = None

    @validator("userId")
    def validate_non_blank_user_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class VlmSourceImagePayload(ApiSchema):
    imageKey: str
    imageUrl: str | None = None
    contentType: str | None = None


class VlmGenerationConfigPayload(ApiSchema):
    modelKey: str | None = None
    quantization: Literal["none", "8bit", "4bit"] | None = None
    dtype: Literal["float16", "bfloat16", "float32"] | None = None
    prompt: str | None = None
    maxNewTokens: int | None = Field(default=None, ge=1)
    numBeams: int | None = Field(default=None, ge=1)


class VlmInferenceRequestPayload(ApiSchema):
    requestId: str
    taskType: Literal["caption", "metadata"]
    memoryId: str | None = None
    userId: str
    capturedAt: str | None = None
    sourceImage: VlmSourceImagePayload
    generation: VlmGenerationConfigPayload | None = None


class CaptureSourceImageSnapshot(ApiSchema):
    imageKey: str
    imageUrl: str | None = None
    contentType: str | None = None
    fileName: str | None = None


class CaptureDispatchPlan(ApiSchema):
    transport: Literal["celery-redis"] = "celery-redis"
    taskName: Literal["process_vision_inference"] = "process_vision_inference"
    status: Literal["prepared"] = "prepared"
    brokerUrl: str | None = None
    note: str


class CaptureUploadResponse(ApiSchema):
    status: Literal["accepted"] = "accepted"
    service: Literal["api-server"] = "api-server"
    captureId: str
    requestId: str
    memoryId: str
    userId: str
    taskType: Literal["caption", "metadata"]
    capturedAt: str
    sourceImage: CaptureSourceImageSnapshot
    inferenceRequest: VlmInferenceRequestPayload
    dispatch: CaptureDispatchPlan


class CaptureWorkerExecutionPayload(ApiSchema):
    taskId: str | None = None
    status: Literal["success", "error", "timeout"]
    result: dict[str, Any] | None = None
    error: str | None = None


class CaptureRagIndexExecutionPayload(ApiSchema):
    endpoint: str
    status: Literal["success", "error", "skipped"]
    indexedCount: int | None = None
    totalUserMemories: dict[str, int] = Field(default_factory=dict)
    response: dict[str, Any] | None = None
    error: str | None = None


class CaptureProcessingResponse(ApiSchema):
    status: Literal["completed", "partial", "failed"]
    service: Literal["api-server"] = "api-server"
    capture: CaptureUploadResponse
    worker: CaptureWorkerExecutionPayload
    ragIndex: CaptureRagIndexExecutionPayload | None = None


class HealthPayload(ApiSchema):
    status: Literal["ok"]
    service: Literal["api-server"]
    checkType: Literal["liveness", "readiness"]
    timestamp: str
