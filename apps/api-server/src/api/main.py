from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.auth import (
    require_internal_service_token,
    resolve_authenticated_principal,
    resolve_authenticated_user,
)
from src.api.intake import build_capture_upload_response
from src.api.pipeline import CapturePipelineError, build_default_capture_pipeline
from src.api.schemas import (
    AuthLoginRequest,
    AuthLogoutRequest,
    AuthLogoutResponse,
    AuthRefreshRequest,
    AuthSignupRequest,
    AuthTokenResponse,
    AuthUserPayload,
    CaptureAcceptedResponse,
    CaptureMemoryStoreExecutionPayload,
    CaptureUploadResponse,
    CaptureTaskStatusResponse,
    CaptureUploadRequest,
    CaptureWorkerExecutionPayload,
    DeviceRegistrationRequest,
    DeviceRegistrationResponse,
    MediaBatchAccessUrlRequest,
    MediaBatchAccessUrlResponse,
    MediaAccessUrlRequest,
    MediaAccessUrlResponse,
    MediaGalleryItemPayload,
    MediaGalleryRequest,
    MediaGalleryResponse,
    MemoryChatRequest,
    MemoryChatResponse,
    MemoryInferenceResultIngestResponse,
    MemoryLocationPayload,
    MemorySearchHitPayload,
    MemorySearchRequest,
    MemorySearchResponse,
    UploadAuthorizationPlan,
    UploadAuthorizationRequest,
    UploadAuthorizationResponse,
    UserCreateRequest,
    UserCreateResponse,
    UserDeviceRegistrationRequest,
    VlmInferenceResultPayload,
)
from src.database.memory_store import build_default_memory_store_client
from src.modules.auth.service import build_default_auth_service
from src.modules.media.service import (
    GalleryItem,
    MediaAccessUrl,
    MediaUrlSignerConfigError,
    build_default_media_access_service,
)
from src.modules.search.service import (
    SearchHit,
    build_default_memory_query_service,
)
from src.modules.users.service import build_default_user_device_service


DEFAULT_CORS_ORIGINS = (
    "http://localhost:8081",
    "http://127.0.0.1:8081",
    "http://localhost:19006",
    "http://127.0.0.1:19006",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
)


def _resolve_cors_origins() -> list[str]:
    raw_value = os.getenv("API_CORS_ALLOW_ORIGINS", "").strip()
    if not raw_value:
        return list(DEFAULT_CORS_ORIGINS)
    origins = [
        origin.strip()
        for origin in raw_value.split(",")
        if origin.strip()
    ]
    return origins or list(DEFAULT_CORS_ORIGINS)


def _map_hit(hit: SearchHit) -> MemorySearchHitPayload:
    return MemorySearchHitPayload(
        memoryId=hit.memory.memory_id,
        score=hit.score,
        lexicalScore=hit.lexical_score,
        matchedTerms=hit.matched_terms,
        imageKey=hit.memory.image_key,
        imageUrl=hit.memory.image_url,
        capturedAt=hit.memory.captured_at,
        caption=hit.memory.caption,
        sceneSummary=hit.memory.scene_summary,
        positionHint=hit.memory.position_hint,
        location=MemoryLocationPayload(**hit.memory.location.to_dict()),
        detectedObjects=hit.memory.detected_objects,
        tags=hit.memory.tags,
    )


def _map_media_access_url(result: MediaAccessUrl) -> MediaAccessUrlResponse:
    return MediaAccessUrlResponse(
        imageKey=result.image_key,
        accessUrl=result.access_url,
        expiresAt=result.expires_at,
        expiresInSec=result.expires_in_sec,
    )


def _map_gallery_item(item: GalleryItem) -> MediaGalleryItemPayload:
    return MediaGalleryItemPayload(
        memoryId=item.memory_id,
        imageKey=item.image_key,
        imageUrl=item.image_url,
        capturedAt=item.captured_at,
        caption=item.caption,
        sceneSummary=item.scene_summary,
        positionHint=item.position_hint,
    )


def _schema_to_payload_dict(payload: Any) -> dict[str, Any]:
    if hasattr(payload, "model_dump"):
        return payload.model_dump(exclude_none=False)
    return payload.dict(exclude_none=False)


def _get_capture_pipeline(request: Request):
    pipeline = getattr(request.app.state, "capture_pipeline", None)
    if pipeline is None:
        pipeline = request.app.state.capture_pipeline_factory()
        request.app.state.capture_pipeline = pipeline
    return pipeline


def _get_memory_query_service(request: Request):
    memory_query_service = getattr(request.app.state, "memory_query_service", None)
    if memory_query_service is None:
        memory_query_service = request.app.state.memory_query_service_factory()
        request.app.state.memory_query_service = memory_query_service
    return memory_query_service


def _get_media_access_service(request: Request):
    media_access_service = getattr(request.app.state, "media_access_service", None)
    if media_access_service is None:
        media_access_service = request.app.state.media_access_service_factory()
        request.app.state.media_access_service = media_access_service
    return media_access_service


def _get_memory_store_client(request: Request):
    memory_store_client = getattr(request.app.state, "memory_store_client", None)
    if memory_store_client is None:
        memory_store_client = request.app.state.memory_store_client_factory()
        request.app.state.memory_store_client = memory_store_client
    return memory_store_client


def _get_user_device_service(request: Request):
    user_device_service = getattr(request.app.state, "user_device_service", None)
    if user_device_service is None:
        user_device_service = request.app.state.user_device_service_factory()
        request.app.state.user_device_service = user_device_service
    return user_device_service


def _get_auth_service(request: Request):
    auth_service = getattr(request.app.state, "auth_service", None)
    if auth_service is None:
        auth_service = request.app.state.auth_service_factory()
        request.app.state.auth_service = auth_service
    return auth_service


def _map_auth_profile(profile: Any) -> AuthUserPayload:
    return AuthUserPayload(
        userId=profile.user_id,
        email=profile.email,
        displayName=profile.display_name,
        role=profile.role,
        status=profile.status,
        createdAt=profile.created_at,
        lastLoginAt=profile.last_login_at,
    )


def _map_auth_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, ValueError):
        detail = str(exc)
        if "already registered" in detail:
            return HTTPException(status_code=409, detail=detail)
        if "API_AUTH_JWT_SECRET" in detail or "API_CAPTURE_DATABASE_URL" in detail:
            return HTTPException(status_code=503, detail=detail)
        return HTTPException(status_code=400, detail=detail)
    return HTTPException(status_code=503, detail=str(exc))


def _request_ip_address(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None
    if request.client is None:
        return None
    return request.client.host


def _map_celery_state_to_capture_status(state: str) -> str:
    normalized = " ".join(str(state).split()).strip().upper()
    if normalized in {"PENDING", "RECEIVED"}:
        return "queued"
    if normalized == "STARTED":
        return "running"
    if normalized == "RETRY":
        return "retrying"
    if normalized == "SUCCESS":
        return "completed"
    return "failed"


def _map_user_device_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        detail = str(exc)
        if "API_CAPTURE_DATABASE_URL" in detail or "database_url" in detail:
            return HTTPException(status_code=503, detail=detail)
        if "already registered" in detail:
            return HTTPException(status_code=409, detail=detail)
        return HTTPException(status_code=400, detail=detail)
    return HTTPException(status_code=503, detail=str(exc))


def _authorize_capture_payload(
    request: Request,
    payload: CaptureUploadRequest,
) -> CaptureUploadRequest:
    try:
        user_device_service = _get_user_device_service(request)
        authorization = user_device_service.authorize_device(
            device_id=payload.deviceId
        )
    except Exception as exc:
        raise _map_user_device_error(exc) from exc

    if authorization.status != "allowed" or not authorization.user_id:
        raise HTTPException(
            status_code=403,
            detail="deviceId is not allowed to register captures",
        )

    if payload.userId != authorization.user_id:
        raise HTTPException(
            status_code=403,
            detail="deviceId does not match requested userId",
        )

    if hasattr(payload, "model_copy"):
        return payload.model_copy(
            update={
                "userId": authorization.user_id,
                "deviceId": authorization.device_id,
            }
        )
    return payload.copy(  # type: ignore[no-any-return]
        update={
            "userId": authorization.user_id,
            "deviceId": authorization.device_id,
        }
    )


def _build_upload_authorization_capture(
    *,
    user_id: str,
    device_id: str,
    payload: UploadAuthorizationRequest,
) -> CaptureUploadResponse:
    capture_request = CaptureUploadRequest(
        captureId=payload.captureId,
        requestId=payload.requestId,
        memoryId=payload.memoryId,
        userId=user_id,
        deviceId=device_id,
        taskType=payload.taskType,
        capturedAt=payload.capturedAt,
        fileName=payload.fileName,
        imageKey=payload.imageKey,
        contentType=payload.contentType,
    )
    return build_capture_upload_response(capture_request)


def create_app() -> FastAPI:
    app = FastAPI(
        title="smart-glass-api-server",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_resolve_cors_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def root() -> dict[str, object]:
        return {
            "service": "api-server",
            "status": "ok",
            "routes": [
                "GET /health/live",
                "GET /health/ready",
                "POST /auth/signup",
                "POST /auth/login",
                "POST /auth/refresh",
                "POST /auth/logout",
                "GET /auth/me",
                "POST /users",
                "POST /users/{userId}/devices",
                "POST /devices/register",
                "POST /media/upload-authorizations",
                "POST /media/captures",
                "GET /media/captures/tasks/{taskId}",
                "POST /media/gallery",
                "POST /media/access-url",
                "POST /media/access-urls",
                "POST /memories/inference-results",
                "POST /search",
                "POST /chat",
            ],
            "notes": (
                "This service accepts capture registrations, dispatches the "
                "inference worker, persists successful VLM results into the "
                "shared memory store, and serves memory search/chat queries."
            ),
        }

    app.state.capture_pipeline = None
    app.state.capture_pipeline_factory = build_default_capture_pipeline
    app.state.memory_store_client = None
    app.state.memory_store_client_factory = build_default_memory_store_client
    app.state.media_access_service = None
    app.state.media_access_service_factory = build_default_media_access_service
    app.state.memory_query_service = None
    app.state.memory_query_service_factory = build_default_memory_query_service
    app.state.auth_service = None
    app.state.auth_service_factory = build_default_auth_service
    app.state.user_device_service = None
    app.state.user_device_service_factory = build_default_user_device_service

    @app.get("/health/live")
    async def liveness_check() -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "ok",
                "service": "api-server",
                "checkType": "liveness",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @app.get("/health/ready")
    async def readiness_check(request: Request) -> JSONResponse:
        timestamp = datetime.now(timezone.utc).isoformat()
        checks: dict[str, str] = {}
        errors: dict[str, str] = {}

        try:
            pipeline = _get_capture_pipeline(request)
            pipeline.check_health()
            checks["capturePipeline"] = "ok"
        except Exception as exc:
            checks["capturePipeline"] = "error"
            errors["capturePipeline"] = str(exc)

        try:
            memory_query_service = _get_memory_query_service(request)
            memory_query_service.check_health()
            checks["memoryQuery"] = "ok"
        except Exception as exc:
            checks["memoryQuery"] = "error"
            errors["memoryQuery"] = str(exc)

        try:
            media_access_service = _get_media_access_service(request)
            media_access_service.check_health()
            checks["mediaAccess"] = "ok"
        except Exception as exc:
            checks["mediaAccess"] = "error"
            errors["mediaAccess"] = str(exc)

        try:
            user_device_service = _get_user_device_service(request)
            user_device_service.check_health()
            checks["userDevice"] = "ok"
        except Exception as exc:
            checks["userDevice"] = "error"
            errors["userDevice"] = str(exc)

        if errors:
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={
                    "status": "error",
                    "service": "api-server",
                    "checkType": "readiness",
                    "timestamp": timestamp,
                    "checks": checks,
                    "errors": errors,
                },
            )

        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "ok",
                "service": "api-server",
                "checkType": "readiness",
                "timestamp": timestamp,
                "checks": checks,
            },
        )

    @app.post(
        "/auth/signup",
        status_code=status.HTTP_201_CREATED,
        response_model=AuthTokenResponse,
    )
    def sign_up(
        request: Request,
        payload: AuthSignupRequest,
    ) -> AuthTokenResponse:
        try:
            auth_service = _get_auth_service(request)
            bundle = auth_service.sign_up(
                email=payload.email,
                password=payload.password,
                display_name=payload.displayName,
                user_id=payload.userId,
                device_id=payload.deviceId,
                user_agent=request.headers.get("User-Agent"),
                ip_address=_request_ip_address(request),
            )
        except Exception as exc:
            raise _map_auth_error(exc) from exc
        return AuthTokenResponse(
            accessToken=bundle.access_token,
            refreshToken=bundle.refresh_token,
            expiresInSec=bundle.expires_in_sec,
            refreshExpiresInSec=bundle.refresh_expires_in_sec,
            user=_map_auth_profile(bundle.user),
        )

    @app.post(
        "/auth/login",
        response_model=AuthTokenResponse,
    )
    def login(
        request: Request,
        payload: AuthLoginRequest,
    ) -> AuthTokenResponse:
        try:
            auth_service = _get_auth_service(request)
            bundle = auth_service.login(
                email=payload.email,
                password=payload.password,
                device_id=payload.deviceId,
                user_agent=request.headers.get("User-Agent"),
                ip_address=_request_ip_address(request),
            )
        except Exception as exc:
            raise _map_auth_error(exc) from exc
        return AuthTokenResponse(
            accessToken=bundle.access_token,
            refreshToken=bundle.refresh_token,
            expiresInSec=bundle.expires_in_sec,
            refreshExpiresInSec=bundle.refresh_expires_in_sec,
            user=_map_auth_profile(bundle.user),
        )

    @app.post(
        "/auth/refresh",
        response_model=AuthTokenResponse,
    )
    def refresh_auth_token(
        request: Request,
        payload: AuthRefreshRequest,
    ) -> AuthTokenResponse:
        try:
            auth_service = _get_auth_service(request)
            bundle = auth_service.refresh(
                refresh_token=payload.refreshToken,
                user_agent=request.headers.get("User-Agent"),
                ip_address=_request_ip_address(request),
            )
        except Exception as exc:
            raise _map_auth_error(exc) from exc
        return AuthTokenResponse(
            accessToken=bundle.access_token,
            refreshToken=bundle.refresh_token,
            expiresInSec=bundle.expires_in_sec,
            refreshExpiresInSec=bundle.refresh_expires_in_sec,
            user=_map_auth_profile(bundle.user),
        )

    @app.post(
        "/auth/logout",
        response_model=AuthLogoutResponse,
    )
    def logout(
        request: Request,
        payload: AuthLogoutRequest | None = None,
    ) -> AuthLogoutResponse:
        payload = payload or AuthLogoutRequest()
        authorization = request.headers.get("Authorization", "").strip()
        _, _, bearer_token = authorization.partition(" ")
        normalized_access_token = bearer_token.strip() or None
        if normalized_access_token and normalized_access_token.startswith("demo-user:"):
            normalized_access_token = None
        try:
            auth_service = _get_auth_service(request)
            outcome = auth_service.logout(
                refresh_token=payload.refreshToken,
                access_token=normalized_access_token,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except Exception as exc:
            raise _map_auth_error(exc) from exc
        return AuthLogoutResponse(
            revokedAccessToken=outcome.revoked_access_token,
            revokedRefreshToken=outcome.revoked_refresh_token,
        )

    @app.get(
        "/auth/me",
        response_model=AuthUserPayload,
    )
    def get_current_auth_user(request: Request) -> AuthUserPayload:
        principal = resolve_authenticated_principal(request)
        try:
            auth_service = _get_auth_service(request)
            profile = auth_service.get_user_profile(principal.user_id)
        except Exception as exc:
            raise _map_auth_error(exc) from exc
        return _map_auth_profile(profile)

    @app.post(
        "/users",
        status_code=status.HTTP_201_CREATED,
        response_model=UserCreateResponse,
    )
    def create_user(
        request: Request,
        payload: UserCreateRequest | None = None,
    ) -> UserCreateResponse:
        payload = payload or UserCreateRequest()
        try:
            user_device_service = _get_user_device_service(request)
            user = user_device_service.create_user(user_id=payload.userId)
        except Exception as exc:
            raise _map_user_device_error(exc) from exc
        return UserCreateResponse(
            userId=user.user_id,
            createdAt=user.created_at,
        )

    @app.post(
        "/devices/register",
        status_code=status.HTTP_201_CREATED,
        response_model=DeviceRegistrationResponse,
    )
    def register_device(
        request: Request,
        payload: DeviceRegistrationRequest,
    ) -> DeviceRegistrationResponse:
        try:
            user_device_service = _get_user_device_service(request)
            device = user_device_service.register_device(
                user_id=payload.userId,
                device_id=payload.deviceId,
            )
        except Exception as exc:
            raise _map_user_device_error(exc) from exc
        return DeviceRegistrationResponse(
            userId=device.user_id,
            deviceId=device.device_id,
            registeredAt=device.registered_at,
        )

    @app.post(
        "/users/{userId}/devices",
        status_code=status.HTTP_201_CREATED,
        response_model=DeviceRegistrationResponse,
    )
    def register_device_for_user(
        request: Request,
        userId: str,
        payload: UserDeviceRegistrationRequest,
    ) -> DeviceRegistrationResponse:
        try:
            user_device_service = _get_user_device_service(request)
            device = user_device_service.register_device(
                user_id=userId,
                device_id=payload.deviceId,
            )
        except Exception as exc:
            raise _map_user_device_error(exc) from exc
        return DeviceRegistrationResponse(
            userId=device.user_id,
            deviceId=device.device_id,
            registeredAt=device.registered_at,
        )

    @app.post(
        "/media/upload-authorizations",
        response_model=UploadAuthorizationResponse,
    )
    def authorize_media_upload(
        request: Request,
        payload: UploadAuthorizationRequest,
    ) -> UploadAuthorizationResponse | JSONResponse:
        try:
            user_device_service = _get_user_device_service(request)
            authorization = user_device_service.authorize_device(
                device_id=payload.deviceId
            )
        except Exception as exc:
            raise _map_user_device_error(exc) from exc

        upload_plan = None
        if authorization.status == "allowed" and authorization.user_id:
            try:
                capture = _build_upload_authorization_capture(
                    user_id=authorization.user_id,
                    device_id=authorization.device_id,
                    payload=payload,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            try:
                media_access_service = _get_media_access_service(request)
                upload_url = media_access_service.issue_upload_url(
                    image_key=capture.sourceImage.imageKey,
                    content_type=capture.sourceImage.contentType,
                )
            except MediaUrlSignerConfigError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except RuntimeError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            upload_plan = UploadAuthorizationPlan(
                captureId=capture.captureId,
                requestId=capture.requestId,
                memoryId=capture.memoryId,
                taskType=capture.taskType,
                capturedAt=capture.capturedAt,
                uploadUrl=upload_url.access_url,
                expiresAt=upload_url.expires_at,
                expiresInSec=upload_url.expires_in_sec,
                sourceImage=capture.sourceImage,
            )

        response = UploadAuthorizationResponse(
            status=authorization.status,
            deviceId=authorization.device_id,
            userId=authorization.user_id,
            upload=upload_plan,
        )
        if authorization.status == "blocked":
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content=_schema_to_payload_dict(response),
            )
        return response

    @app.post(
        "/media/captures",
        status_code=status.HTTP_202_ACCEPTED,
        response_model=CaptureAcceptedResponse,
    )
    async def register_capture(
        request: Request, payload: CaptureUploadRequest
    ) -> CaptureAcceptedResponse:
        payload = _authorize_capture_payload(request, payload)
        try:
            pipeline = _get_capture_pipeline(request)
            task_id, capture = pipeline.submit(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except CapturePipelineError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return CaptureAcceptedResponse(
            status="accepted",
            taskId=task_id,
            capture=capture,
            worker=CaptureWorkerExecutionPayload(
                taskId=task_id,
                status="queued",
                result=None,
                error=None,
            ),
        )

    @app.get(
        "/media/captures/tasks/{taskId}",
        response_model=CaptureTaskStatusResponse,
    )
    async def get_capture_task_status(
        request: Request,
        taskId: str,
    ) -> CaptureTaskStatusResponse:
        try:
            pipeline = _get_capture_pipeline(request)
            task_status = pipeline.get_task_status(taskId)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except CapturePipelineError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        response_status = _map_celery_state_to_capture_status(task_status.state)
        memory_store_payload = None
        worker_status = response_status
        if worker_status == "completed":
            worker_status = "success"
        elif worker_status == "failed":
            worker_status = "error"
        worker_payload = CaptureWorkerExecutionPayload(
            taskId=task_status.task_id,
            status=worker_status,
            result=task_status.result,
            error=task_status.error,
        )

        if response_status == "completed":
            worker_result = task_status.result or {}
            response_status, memory_store_payload = pipeline.build_memory_store_payload(
                worker_result
            )
            if response_status == "failed":
                worker_payload = CaptureWorkerExecutionPayload(
                    taskId=task_status.task_id,
                    status="error",
                    result=worker_result,
                    error=memory_store_payload.error if memory_store_payload else None,
                )
        elif response_status == "failed":
            worker_payload = CaptureWorkerExecutionPayload(
                taskId=task_status.task_id,
                status="error",
                result=None,
                error=task_status.error or f"Inference task ended with state {task_status.state}",
            )
            memory_store_payload = CaptureMemoryStoreExecutionPayload(
                backend=(
                    pipeline.memory_store_client.backend_name
                    if pipeline.memory_store_client is not None
                    else "disabled"
                ),
                status="skipped",
                storedCount=None,
                totalUserMemories={},
                error=worker_payload.error,
            )

        return CaptureTaskStatusResponse(
            status=response_status,
            taskId=task_status.task_id,
            worker=worker_payload,
            memoryStore=memory_store_payload,
        )

    @app.post("/media/gallery", response_model=MediaGalleryResponse)
    def get_media_gallery(
        request: Request,
        payload: MediaGalleryRequest,
    ) -> MediaGalleryResponse:
        user_id = resolve_authenticated_user(request, payload.userId)
        try:
            media_access_service = _get_media_access_service(request)
            items = media_access_service.list_gallery_items(
                user_id=user_id,
                limit=payload.limit,
            )
        except MediaUrlSignerConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return MediaGalleryResponse(
            totalItems=len(items),
            items=[_map_gallery_item(item) for item in items],
        )

    @app.post("/media/access-url", response_model=MediaAccessUrlResponse)
    def issue_media_access_url(
        request: Request,
        payload: MediaAccessUrlRequest,
    ) -> MediaAccessUrlResponse:
        user_id = resolve_authenticated_user(request, payload.userId)
        try:
            media_access_service = _get_media_access_service(request)
            result = media_access_service.issue_access_url(
                user_id=user_id,
                image_key=payload.imageKey,
                expires_in_sec=payload.expiresInSec,
            )
        except MediaUrlSignerConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return _map_media_access_url(result)

    @app.post("/media/access-urls", response_model=MediaBatchAccessUrlResponse)
    def issue_media_access_urls(
        request: Request,
        payload: MediaBatchAccessUrlRequest,
    ) -> MediaBatchAccessUrlResponse:
        user_id = resolve_authenticated_user(request, payload.userId)
        try:
            media_access_service = _get_media_access_service(request)
            items = media_access_service.issue_access_urls(
                user_id=user_id,
                image_keys=payload.imageKeys,
                expires_in_sec=payload.expiresInSec,
            )
        except MediaUrlSignerConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return MediaBatchAccessUrlResponse(
            totalItems=len(items),
            items=[_map_media_access_url(item) for item in items],
        )

    @app.post(
        "/memories/inference-results",
        status_code=status.HTTP_201_CREATED,
        response_model=MemoryInferenceResultIngestResponse,
    )
    def store_inference_result(
        request: Request,
        payload: VlmInferenceResultPayload,
    ) -> MemoryInferenceResultIngestResponse:
        require_internal_service_token(request)
        try:
            memory_store_client = _get_memory_store_client(request)
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Memory store backend unavailable: {exc}",
            ) from exc

        try:
            outcome = memory_store_client.persist_vlm_result(
                _schema_to_payload_dict(payload)
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Memory store backend unavailable: {exc}",
            ) from exc

        return MemoryInferenceResultIngestResponse(
            memoryId=payload.memoryId,
            userId=payload.userId,
            imageKey=payload.sourceImage.imageKey,
            capturedAt=payload.capturedAt,
            storedCount=outcome.stored_count,
            totalUserMemories=outcome.total_user_memories,
        )

    @app.post("/search", response_model=MemorySearchResponse)
    def search_memories(
        request: Request,
        payload: MemorySearchRequest,
    ) -> MemorySearchResponse:
        user_id = resolve_authenticated_user(request, payload.userId)
        try:
            memory_query_service = _get_memory_query_service(request)
            hits = memory_query_service.search(
                user_id=user_id,
                query=payload.query,
                top_k=payload.topK,
            )
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Memory query backend unavailable: {exc}",
            ) from exc

        return MemorySearchResponse(
            query=payload.query,
            totalHits=len(hits),
            hits=[_map_hit(hit) for hit in hits],
        )

    @app.post("/chat", response_model=MemoryChatResponse)
    def chat_with_memories(
        request: Request,
        payload: MemoryChatRequest,
    ) -> MemoryChatResponse:
        user_id = resolve_authenticated_user(request, payload.userId)
        try:
            memory_query_service = _get_memory_query_service(request)
            answer_result, hits = memory_query_service.chat(
                user_id=user_id,
                query=payload.query,
                top_k=payload.topK,
            )
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Memory query backend unavailable: {exc}",
            ) from exc

        return MemoryChatResponse(
            answer=answer_result.text,
            answerMode=answer_result.mode,
            query=payload.query,
            totalHits=len(hits),
            hits=[_map_hit(hit) for hit in hits],
            citedMemoryIds=answer_result.cited_memory_ids,
            confidence=answer_result.confidence,
            reason=answer_result.reason,
        )

    return app


app = create_app()
