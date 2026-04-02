from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.logging import get_logger


logger = get_logger(__name__)


def _build_error_response(
    request: Request,
    *,
    status_code: int,
    error_code: str,
    message: str,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": error_code,
                "message": message,
                "request_id": request_id,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        logger.warning(
            "Handled HTTP exception",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "method": request.method,
                "path": request.url.path,
                "status_code": exc.status_code,
            },
        )
        return _build_error_response(
            request,
            status_code=exc.status_code,
            error_code="http_error",
            message=str(exc.detail),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception(
            "Unhandled server exception",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "method": request.method,
                "path": request.url.path,
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            },
        )
        return _build_error_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            error_code="internal_server_error",
            message="Internal server error",
        )
