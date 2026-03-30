import time
import uuid
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from src.core.logging import get_logger


logger = get_logger(__name__)


class RequestContextLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Response]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        started_at = time.perf_counter()
        response: Response | None = None

        try:
            response = await call_next(request)
            return response
        finally:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            status_code = response.status_code if response is not None else 500
            client_ip = request.client.host if request.client else None

            logger.info(
                "HTTP request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                },
            )

            if response is not None:
                response.headers["x-request-id"] = request_id
