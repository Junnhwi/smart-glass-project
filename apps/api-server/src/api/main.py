from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from src.api.pipeline import CapturePipelineError, build_default_capture_pipeline
from src.api.schemas import (
    CaptureProcessingResponse,
    CaptureUploadRequest,
    MemoryChatRequest,
    MemoryChatResponse,
    MemoryLocationPayload,
    MemorySearchHitPayload,
    MemorySearchRequest,
    MemorySearchResponse,
)
from src.modules.search.service import (
    SearchHit,
    build_default_memory_query_service,
)


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


def create_app() -> FastAPI:
    app = FastAPI(
        title="smart-glass-api-server",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
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

    @app.post("/search", response_model=MemorySearchResponse)
    def search_memories(
        request: Request,
        payload: MemorySearchRequest,
    ) -> MemorySearchResponse:
        try:
            memory_query_service = _get_memory_query_service(request)
            hits = memory_query_service.search(
                user_id=payload.userId,
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
        try:
            memory_query_service = _get_memory_query_service(request)
            answer_result, hits = memory_query_service.chat(
                user_id=payload.userId,
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
