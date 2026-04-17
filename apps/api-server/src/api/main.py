from __future__ import annotations

from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from src.api.pipeline import CapturePipelineError, build_default_capture_pipeline
from src.api.schemas import (
    CaptureProcessingResponse,
    CaptureUploadRequest,
)


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
            ],
            "notes": (
                "This service accepts capture registrations, dispatches the "
                "inference worker, and can optionally forward successful "
                "VLM results to downstream indexing services."
            ),
        }

    app.state.capture_pipeline = None
    app.state.capture_pipeline_factory = build_default_capture_pipeline

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
    async def readiness_check() -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "ok",
                "service": "api-server",
                "checkType": "readiness",
                "timestamp": datetime.now(timezone.utc).isoformat(),
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
            pipeline = getattr(request.app.state, "capture_pipeline", None)
            if pipeline is None:
                pipeline = request.app.state.capture_pipeline_factory()
                request.app.state.capture_pipeline = pipeline
            response = pipeline.process(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except CapturePipelineError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return response

    return app


app = create_app()
