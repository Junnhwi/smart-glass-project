from typing import Any

from fastapi import APIRouter, Request

from src.api.schemas import (
    VisionInferenceEnqueueRequest,
    VisionInferenceEnqueueResponse,
    VisionInferenceTaskStatusResponse,
)
from src.queue.tasks import app as celery_app
from src.queue.tasks import process_vision_inference

router = APIRouter()


def _map_task_status(state: str, ready: bool, successful: bool) -> str:
    if not ready:
        if state in {"STARTED", "RETRY", "PROGRESS"}:
            return "running"
        return "pending"
    if successful:
        return "completed"
    return "failed"


@router.post(
    "/tasks/vision",
    response_model=VisionInferenceEnqueueResponse,
    status_code=202,
)
async def enqueue_vision_inference(
    request: Request,
    payload: VisionInferenceEnqueueRequest,
) -> VisionInferenceEnqueueResponse:
    resolved_request_id = payload.request_id or getattr(
        request.state, "request_id", None
    )
    async_result = process_vision_inference.apply_async(
        kwargs={
            "image_key": payload.image_key,
            "user_id": payload.user_id,
            "memory_id": payload.memory_id,
            "captured_at": payload.captured_at,
            "image_url": payload.image_url,
            "request_id": resolved_request_id,
            "task_type": payload.task_type,
        }
    )
    return VisionInferenceEnqueueResponse(
        taskId=async_result.id,
        state=async_result.state,
        requestId=resolved_request_id or async_result.id,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=VisionInferenceTaskStatusResponse,
)
async def get_vision_inference_task(task_id: str) -> VisionInferenceTaskStatusResponse:
    async_result = celery_app.AsyncResult(task_id)
    ready = async_result.ready()
    successful = async_result.successful() if ready else False

    result_payload: dict[str, Any] | None = None
    error_message: str | None = None
    if ready:
        result = async_result.result
        if isinstance(result, dict):
            result_payload = result
        elif result is not None:
            error_message = str(result)
        if async_result.failed() and error_message is None:
            error_message = str(async_result.result)

    request_id = None
    if isinstance(result_payload, dict):
        raw_request_id = result_payload.get("requestId")
        if raw_request_id is not None:
            request_id = str(raw_request_id).strip() or None

    return VisionInferenceTaskStatusResponse(
        taskId=task_id,
        state=async_result.state,
        ready=ready,
        successful=successful,
        requestId=request_id,
        result=result_payload,
        error=error_message,
        taskStatus=_map_task_status(async_result.state, ready, successful),
    )
