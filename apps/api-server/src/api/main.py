from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.auth import (
    require_internal_service_token,
    resolve_authenticated_user,
)
from src.api.pipeline import CapturePipelineError, build_default_capture_pipeline
from src.api.schemas import (
    CaptureProcessingResponse,
    CaptureUploadRequest,
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
    VlmInferenceResultPayload,
)
from src.database.memory_store import build_default_memory_store_client
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
                "POST /media/captures",
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
        "/media/captures",
        status_code=status.HTTP_200_OK,
        response_model=CaptureProcessingResponse,
    )
    def register_capture(
        request: Request, payload: CaptureUploadRequest
    ) -> CaptureProcessingResponse:
        try:
            pipeline = _get_capture_pipeline(request)
            response = pipeline.process(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except CapturePipelineError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return response

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
