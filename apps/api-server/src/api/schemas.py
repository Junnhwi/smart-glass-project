from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, validator

try:
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover - pydantic v1 fallback
    ConfigDict = None

try:
    from pydantic import root_validator
except ImportError:  # pragma: no cover - pydantic v2 fallback
    root_validator = None


class ApiSchema(BaseModel):
    if ConfigDict is not None:
        model_config = ConfigDict(
            extra="ignore",
            str_strip_whitespace=True,
            populate_by_name=True,
        )
    else:
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
    deviceId: str = Field(min_length=1)
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

    @validator("deviceId")
    def validate_non_blank_device_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class VlmSourceImagePayload(ApiSchema):
    imageKey: str = Field(min_length=1)
    imageUrl: str | None = None
    contentType: str | None = None

    @validator("imageKey")
    def validate_non_blank_image_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


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


class VlmInferenceLocationPayload(ApiSchema):
    name: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class VlmInferenceMetadataPayload(ApiSchema):
    caption: str | None = None
    sceneSummary: str | None = None
    detectedObjects: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    ocrText: str | None = None
    positionHint: str | None = None
    location: VlmInferenceLocationPayload | None = None


class VlmObjectVisualFeaturesPayload(ApiSchema):
    brand: str | None = None
    color: str | None = None
    text: str | None = None


class VlmStructuredObjectPayload(ApiSchema):
    name: str = Field(min_length=1)
    nearby_objects: list[str] = Field(default_factory=list)
    visual_features: VlmObjectVisualFeaturesPayload | None = None

    @validator("name")
    def validate_non_blank_object_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class VlmPipelineOutputPayload(ApiSchema):
    scene_summary: str | None = None
    location_context: str | None = None
    objects: list[VlmStructuredObjectPayload] = Field(default_factory=list)


class VlmProviderCapabilitiesPayload(ApiSchema):
    detectedObjects: bool = True
    tags: bool = True
    positionHint: bool = True
    sceneSummary: bool = True
    ocrText: bool = True
    location: bool = True


class VlmProviderMetadataPayload(ApiSchema):
    modelKey: str | None = None
    modelId: str | None = None
    modelFamily: str | None = None
    quantization: Literal["none", "8bit", "4bit"] | None = None
    dtype: Literal["float16", "bfloat16", "float32"] | None = None
    provider: str | None = None
    capabilities: VlmProviderCapabilitiesPayload | None = None
    executionPolicy: dict[str, Any] | None = None
    raw: dict[str, Any] | None = None


class VlmRuntimePayload(ApiSchema):
    latencySec: float | None = Field(default=None, ge=0)
    peakMemoryMb: float | None = Field(default=None, ge=0)
    loadTimeSec: float | None = Field(default=None, ge=0)


class VlmInferenceResultPayload(ApiSchema):
    status: Literal["success"] = "success"
    requestId: str = Field(min_length=1)
    taskType: Literal["caption", "metadata"] = "metadata"
    memoryId: str = Field(min_length=1)
    userId: str = Field(min_length=1)
    capturedAt: str = Field(min_length=1)
    sourceImage: VlmSourceImagePayload
    metadata: VlmInferenceMetadataPayload
    pipelineOutput: VlmPipelineOutputPayload = Field(default_factory=VlmPipelineOutputPayload)
    providerMetadata: VlmProviderMetadataPayload | None = None
    runtime: VlmRuntimePayload | None = None

    @validator("requestId", "memoryId", "userId", "capturedAt")
    def validate_non_blank_result_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


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
    status: Literal["queued", "running", "retrying", "success", "error", "timeout"]
    result: dict[str, Any] | None = None
    error: str | None = None


class CaptureMemoryStoreExecutionPayload(ApiSchema):
    backend: str
    status: Literal["success", "error", "skipped"]
    storedCount: int | None = None
    totalUserMemories: dict[str, int] = Field(default_factory=dict)
    error: str | None = None


class CaptureProcessingResponse(ApiSchema):
    status: Literal["completed", "partial", "failed"]
    service: Literal["api-server"] = "api-server"
    capture: CaptureUploadResponse
    worker: CaptureWorkerExecutionPayload
    memoryStore: CaptureMemoryStoreExecutionPayload | None = None


class CaptureAcceptedResponse(ApiSchema):
    status: Literal["accepted"] = "accepted"
    service: Literal["api-server"] = "api-server"
    taskId: str
    capture: CaptureUploadResponse
    worker: CaptureWorkerExecutionPayload


class CaptureTaskStatusResponse(ApiSchema):
    status: Literal["queued", "running", "retrying", "completed", "partial", "failed"]
    service: Literal["api-server"] = "api-server"
    taskId: str
    worker: CaptureWorkerExecutionPayload
    memoryStore: CaptureMemoryStoreExecutionPayload | None = None


class UserCreateRequest(ApiSchema):
    userId: str | None = None

    @validator("userId")
    def validate_optional_non_blank_user_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class UserCreateResponse(ApiSchema):
    status: Literal["created"] = "created"
    userId: str
    createdAt: str


class DeviceRegistrationRequest(ApiSchema):
    userId: str = Field(min_length=1)
    deviceId: str = Field(min_length=1)

    @validator("userId", "deviceId")
    def validate_non_blank_device_registration_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class UserDeviceRegistrationRequest(ApiSchema):
    deviceId: str = Field(min_length=1)

    @validator("deviceId")
    def validate_non_blank_user_device_registration_device_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class DeviceRegistrationResponse(ApiSchema):
    status: Literal["registered"] = "registered"
    userId: str
    deviceId: str
    registeredAt: str


class UserDevicePayload(ApiSchema):
    userId: str
    deviceId: str
    status: Literal["active", "revoked"]
    registeredAt: str
    approvedAt: str | None = None
    revokedAt: str | None = None
    updatedAt: str | None = None


class UserDeviceListResponse(ApiSchema):
    status: Literal["ok"] = "ok"
    userId: str
    totalDevices: int
    items: list[UserDevicePayload]


class UserDeviceStatusResponse(ApiSchema):
    status: Literal["active", "revoked"]
    userId: str
    deviceId: str
    registeredAt: str
    approvedAt: str | None = None
    revokedAt: str | None = None
    updatedAt: str | None = None


class DevicePairingIssueRequest(ApiSchema):
    deviceId: str = Field(min_length=1)

    @validator("deviceId")
    def validate_non_blank_device_pairing_device_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class DevicePairingPayload(ApiSchema):
    pairingCode: str
    userId: str
    deviceId: str
    status: Literal["pending", "approved", "rejected"]
    createdAt: str
    expiresAt: str
    approvedAt: str | None = None
    updatedAt: str | None = None


class DevicePairingIssueResponse(ApiSchema):
    status: Literal["issued"] = "issued"
    pairing: DevicePairingPayload


class DevicePairingListResponse(ApiSchema):
    status: Literal["ok"] = "ok"
    totalPairings: int
    items: list[DevicePairingPayload]


class AuthUserPayload(ApiSchema):
    userId: str
    email: str
    displayName: str
    role: Literal["user", "admin"]
    status: Literal["active", "disabled"]
    createdAt: str
    lastLoginAt: str | None = None


class AuthAdminUserListResponse(ApiSchema):
    status: Literal["ok"] = "ok"
    totalUsers: int
    items: list[AuthUserPayload]


class AuthAdminUserUpdateRequest(ApiSchema):
    displayName: str | None = None
    role: Literal["user", "admin"] | None = None
    status: Literal["active", "disabled"] | None = None

    @validator("displayName")
    def validate_optional_non_blank_admin_display_name(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    if root_validator is not None:

        @root_validator(skip_on_failure=True)
        def validate_admin_update_has_changes(
            cls,
            values: dict[str, Any],
        ) -> dict[str, Any]:
            if (
                values.get("displayName") is None
                and values.get("role") is None
                and values.get("status") is None
            ):
                raise ValueError(
                    "at least one of displayName, role, status is required"
                )
            return values


class AuthAdminUserUpdateResponse(ApiSchema):
    status: Literal["updated"] = "updated"
    user: AuthUserPayload
    revokedSessionCount: int = 0


class AuthSignupRequest(ApiSchema):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    displayName: str | None = None
    userId: str | None = None
    deviceId: str | None = None

    @validator("email", "password")
    def validate_non_blank_auth_signup_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @validator("displayName", "userId", "deviceId")
    def validate_optional_signup_strings(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class AuthLoginRequest(ApiSchema):
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)
    deviceId: str | None = None

    @validator("email", "password")
    def validate_non_blank_auth_login_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @validator("deviceId")
    def validate_optional_login_device_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class AuthRefreshRequest(ApiSchema):
    refreshToken: str = Field(min_length=1)

    @validator("refreshToken")
    def validate_non_blank_refresh_token(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class AuthLogoutRequest(ApiSchema):
    refreshToken: str | None = None

    @validator("refreshToken")
    def validate_optional_non_blank_logout_refresh_token(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class AuthTokenResponse(ApiSchema):
    status: Literal["authenticated"] = "authenticated"
    tokenType: Literal["Bearer"] = "Bearer"
    accessToken: str
    refreshToken: str
    expiresInSec: int = Field(ge=60)
    refreshExpiresInSec: int = Field(ge=300)
    user: AuthUserPayload


class AuthLogoutResponse(ApiSchema):
    status: Literal["logged_out"] = "logged_out"
    revokedAccessToken: bool
    revokedRefreshToken: bool


class AuthOauthStartRequest(ApiSchema):
    redirectUri: str = Field(min_length=1)

    @validator("redirectUri")
    def validate_non_blank_oauth_redirect_uri(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class AuthOauthStartResponse(ApiSchema):
    provider: Literal["google"]
    authorizationUrl: str
    state: str
    expiresAt: str


class AuthOauthExchangeRequest(ApiSchema):
    handoffCode: str = Field(min_length=1)
    deviceId: str | None = None

    @validator("handoffCode")
    def validate_non_blank_oauth_handoff_code(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @validator("deviceId")
    def validate_optional_oauth_device_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class UploadAuthorizationRequest(ApiSchema):
    deviceId: str = Field(min_length=1)
    captureId: str | None = None
    requestId: str | None = None
    memoryId: str | None = None
    taskType: Literal["caption", "metadata"] = "metadata"
    capturedAt: str | None = None
    fileName: str | None = None
    imageKey: str | None = None
    contentType: str | None = None

    @validator("deviceId")
    def validate_non_blank_upload_authorization_device_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @validator(
        "captureId",
        "requestId",
        "memoryId",
        "capturedAt",
        "fileName",
        "imageKey",
        "contentType",
    )
    def validate_optional_upload_authorization_strings(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class UploadAuthorizationPlan(ApiSchema):
    method: Literal["direct"] = "direct"
    captureId: str
    requestId: str
    memoryId: str
    taskType: Literal["caption", "metadata"]
    capturedAt: str
    uploadUrl: str
    expiresAt: str
    expiresInSec: int = Field(ge=30, le=3600)
    sourceImage: CaptureSourceImageSnapshot


class UploadAuthorizationResponse(ApiSchema):
    status: Literal["allowed", "blocked"]
    deviceId: str
    userId: str | None = None
    upload: UploadAuthorizationPlan | None = None


class MediaAccessUrlRequest(ApiSchema):
    userId: str = Field(min_length=1)
    imageKey: str = Field(min_length=1)
    expiresInSec: int = Field(default=300, ge=30, le=3600)

    @validator("userId", "imageKey")
    def validate_non_blank_media_access_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class MediaAccessUrlResponse(ApiSchema):
    imageKey: str
    accessUrl: str
    expiresAt: str
    expiresInSec: int


class MediaBatchAccessUrlRequest(ApiSchema):
    userId: str = Field(min_length=1)
    imageKeys: list[str] = Field(min_items=1, max_items=100)
    expiresInSec: int = Field(default=300, ge=30, le=3600)

    @validator("userId")
    def validate_non_blank_media_batch_user_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @validator("imageKeys")
    def validate_image_keys(cls, image_keys: list[str]) -> list[str]:
        normalized_values = [
            " ".join(value.split())
            for value in image_keys
            if " ".join(value.split())
        ]
        if not normalized_values:
            raise ValueError("must include at least one non-blank imageKey")
        return normalized_values


class MediaBatchAccessUrlResponse(ApiSchema):
    totalItems: int
    items: list[MediaAccessUrlResponse]


class MediaGalleryRequest(ApiSchema):
    userId: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)

    @validator("userId")
    def validate_non_blank_media_gallery_user_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class MediaGalleryItemPayload(ApiSchema):
    memoryId: str
    imageKey: str
    imageUrl: str | None = None
    capturedAt: str | None = None
    caption: str | None = None
    sceneSummary: str | None = None
    positionHint: str | None = None


class MediaGalleryResponse(ApiSchema):
    totalItems: int
    items: list[MediaGalleryItemPayload]


class MemoryInferenceResultIngestResponse(ApiSchema):
    status: Literal["stored"] = "stored"
    memoryId: str
    userId: str
    imageKey: str
    capturedAt: str
    storedCount: int
    totalUserMemories: dict[str, int] = Field(default_factory=dict)


class MemoryLocationPayload(ApiSchema):
    name: str | None = None
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class MemorySearchRequest(ApiSchema):
    userId: str = Field(alias="user_id", min_length=1)
    query: str = Field(min_length=1)
    topK: int = Field(default=5, alias="top_k", ge=1, le=20)

    if root_validator is not None:
        @root_validator(pre=True)
        def populate_search_aliases(cls, values: dict[str, Any]) -> dict[str, Any]:
            values = dict(values or {})
            if "userId" in values and "user_id" not in values:
                values["user_id"] = values["userId"]
            if "topK" in values and "top_k" not in values:
                values["top_k"] = values["topK"]
            return values

    @validator("userId", "query")
    def validate_non_blank_search_fields(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class MemoryChatRequest(MemorySearchRequest):
    conversationId: str | None = Field(default=None, alias="conversation_id")


class MemorySearchHitPayload(ApiSchema):
    memoryId: str
    score: float
    lexicalScore: float
    matchedTerms: list[str]
    imageKey: str | None = None
    imageUrl: str | None = None
    capturedAt: str | None = None
    caption: str | None = None
    sceneSummary: str | None = None
    positionHint: str | None = None
    location: MemoryLocationPayload
    detectedObjects: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class MemorySearchResponse(ApiSchema):
    query: str
    totalHits: int
    hits: list[MemorySearchHitPayload]


class MemoryRecentItemPayload(ApiSchema):
    memoryId: str
    imageKey: str | None = None
    imageUrl: str | None = None
    capturedAt: str | None = None
    caption: str | None = None
    sceneSummary: str | None = None
    positionHint: str | None = None
    location: MemoryLocationPayload
    detectedObjects: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class MemoryRecentResponse(ApiSchema):
    userId: str
    totalItems: int
    items: list[MemoryRecentItemPayload]


class MemoryChatResponse(ApiSchema):
    answer: str
    answerMode: str
    query: str
    totalHits: int
    hits: list[MemorySearchHitPayload]
    citedMemoryIds: list[str] = Field(default_factory=list)
    confidence: float | None = None
    reason: str | None = None


class AdminMemoryQueryLogPayload(ApiSchema):
    logId: int
    userId: str
    queryType: Literal["search", "chat"]
    queryText: str
    totalHits: int
    answerText: str | None = None
    answerMode: str | None = None
    citedMemoryIds: list[str] = Field(default_factory=list)
    createdAt: str


class AdminMemoryQueryLogListResponse(ApiSchema):
    status: Literal["ok"] = "ok"
    totalLogs: int
    items: list[AdminMemoryQueryLogPayload]


class HealthPayload(ApiSchema):
    status: Literal["ok", "error"]
    service: Literal["api-server"]
    checkType: Literal["liveness", "readiness"]
    timestamp: str
