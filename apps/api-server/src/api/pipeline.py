from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from src.api.intake import build_capture_upload_response, build_worker_task_kwargs
from src.api.schemas import (
    CaptureProcessingResponse,
    CaptureRagIndexExecutionPayload,
    CaptureUploadRequest,
    CaptureWorkerExecutionPayload,
)


@dataclass(frozen=True, slots=True)
class CapturePipelineSettings:
    broker_url: str
    result_backend_url: str
    rag_service_base_url: str
    worker_timeout_sec: float = 180.0
    rag_timeout_sec: float = 30.0
    worker_task_name: str = "process_vision_inference"
    rag_index_path: str = "/memories/index/vlm"


@dataclass(frozen=True, slots=True)
class CaptureTaskOutcome:
    task_id: str | None
    result: dict[str, Any]


class CapturePipelineError(RuntimeError):
    pass


class TaskTransport(Protocol):
    def submit_and_wait(
        self,
        *,
        task_kwargs: dict[str, Any],
        timeout_sec: float,
    ) -> CaptureTaskOutcome: ...


class RagIndexClient(Protocol):
    def index_vlm_result(self, worker_result: dict[str, Any]) -> dict[str, Any]: ...


class CeleryTaskTransport:
    def __init__(
        self,
        *,
        broker_url: str,
        result_backend_url: str,
        task_name: str,
    ) -> None:
        self._broker_url = broker_url
        self._result_backend_url = result_backend_url
        self._task_name = task_name
        self._celery_app = None

    def _get_celery_app(self):
        if self._celery_app is not None:
            return self._celery_app
        try:
            from celery import Celery
        except ImportError as exc:  # pragma: no cover - exercised in Docker
            raise CapturePipelineError(
                "celery is required to dispatch inference tasks"
            ) from exc

        self._celery_app = Celery(
            "api_server_capture_pipeline",
            broker=self._broker_url,
            backend=self._result_backend_url,
        )
        return self._celery_app

    def submit_and_wait(
        self,
        *,
        task_kwargs: dict[str, Any],
        timeout_sec: float,
    ) -> CaptureTaskOutcome:
        celery_app = self._get_celery_app()
        async_result = celery_app.send_task(self._task_name, kwargs=task_kwargs)
        try:
            result = async_result.get(timeout=timeout_sec, propagate=True)
        except Exception as exc:  # pragma: no cover - network/runtime failure
            raise CapturePipelineError(
                f"Inference worker dispatch failed: {exc}"
            ) from exc
        if not isinstance(result, dict):
            raise CapturePipelineError("Inference worker returned an invalid payload")
        return CaptureTaskOutcome(task_id=async_result.id, result=result)


class HttpRagIndexClient:
    def __init__(self, *, base_url: str, request_path: str, timeout_sec: float) -> None:
        self._base_url = base_url.rstrip("/")
        self._request_path = request_path
        self._timeout_sec = timeout_sec

    def index_vlm_result(self, worker_result: dict[str, Any]) -> dict[str, Any]:
        try:
            with httpx.Client(base_url=self._base_url, timeout=self._timeout_sec) as client:
                response = client.post(self._request_path, json={"result": worker_result})
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:  # pragma: no cover - runtime failure
            raise CapturePipelineError(f"rag-service indexing failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise CapturePipelineError("rag-service returned an invalid payload")
        return payload


def _normalize_status(value: Any) -> str:
    return " ".join(str(value).split()).strip().lower()


def _default_float(name: str, fallback: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        return float(raw)
    except ValueError:
        return fallback


def build_default_capture_pipeline() -> "CaptureProcessingPipeline":
    settings = CapturePipelineSettings(
        broker_url=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0").strip()
        or "redis://redis:6379/0",
        result_backend_url=os.getenv(
            "CELERY_RESULT_BACKEND", "redis://redis:6379/1"
        ).strip()
        or "redis://redis:6379/1",
        rag_service_base_url=os.getenv(
            "RAG_SERVICE_URL", "http://rag-service:8000"
        ).strip()
        or "http://rag-service:8000",
        worker_timeout_sec=_default_float("API_CAPTURE_WORKER_TIMEOUT_SEC", 180.0),
        rag_timeout_sec=_default_float("API_CAPTURE_RAG_TIMEOUT_SEC", 30.0),
        worker_task_name=os.getenv(
            "API_CAPTURE_WORKER_TASK_NAME", "process_vision_inference"
        ).strip()
        or "process_vision_inference",
        rag_index_path=os.getenv(
            "RAG_INDEX_PATH", "/memories/index/vlm"
        ).strip()
        or "/memories/index/vlm",
    )
    return CaptureProcessingPipeline.from_settings(settings)


class CaptureProcessingPipeline:
    def __init__(
        self,
        *,
        settings: CapturePipelineSettings,
        task_transport: TaskTransport,
        rag_index_client: RagIndexClient,
    ) -> None:
        self.settings = settings
        self.task_transport = task_transport
        self.rag_index_client = rag_index_client

    @classmethod
    def from_settings(cls, settings: CapturePipelineSettings) -> "CaptureProcessingPipeline":
        task_transport = CeleryTaskTransport(
            broker_url=settings.broker_url,
            result_backend_url=settings.result_backend_url,
            task_name=settings.worker_task_name,
        )
        rag_index_client = HttpRagIndexClient(
            base_url=settings.rag_service_base_url,
            request_path=settings.rag_index_path,
            timeout_sec=settings.rag_timeout_sec,
        )
        return cls(
            settings=settings,
            task_transport=task_transport,
            rag_index_client=rag_index_client,
        )

    def process(self, payload: CaptureUploadRequest) -> CaptureProcessingResponse:
        capture_response = build_capture_upload_response(payload)
        task_kwargs = build_worker_task_kwargs(capture_response)
        task_outcome = self.task_transport.submit_and_wait(
            task_kwargs=task_kwargs,
            timeout_sec=self.settings.worker_timeout_sec,
        )

        worker_result = task_outcome.result
        worker_status = _normalize_status(worker_result.get("status"))
        if worker_status != "success":
            message = worker_result.get("message") or "Inference worker returned an error"
            raise CapturePipelineError(str(message))

        rag_index_result = self.rag_index_client.index_vlm_result(worker_result)
        indexed_count = rag_index_result.get("indexed_count")
        total_user_memories = rag_index_result.get("total_user_memories") or {}
        if not isinstance(total_user_memories, dict):
            total_user_memories = {}

        return CaptureProcessingResponse(
            status="completed",
            capture=capture_response,
            worker=CaptureWorkerExecutionPayload(
                taskId=task_outcome.task_id,
                status="success",
                result=worker_result,
                error=None,
            ),
            ragIndex=CaptureRagIndexExecutionPayload(
                endpoint=self.settings.rag_index_path,
                status="success",
                indexedCount=indexed_count if isinstance(indexed_count, int) else None,
                totalUserMemories=total_user_memories,
                response=rag_index_result,
                error=None,
            ),
        )
