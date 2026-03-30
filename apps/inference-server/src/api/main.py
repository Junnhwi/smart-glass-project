from fastapi import FastAPI

from src.api.errors import register_exception_handlers
from src.api.middleware import RequestContextLoggingMiddleware
from src.core.logging import configure_logging
from src.models.captioning import list_available_caption_models


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title="smart-glass-inference-server",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.add_middleware(RequestContextLoggingMiddleware)
    register_exception_handlers(app)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok", "service": "inference-server"}

    @app.get("/models/captioning")
    async def get_caption_models() -> dict[str, list[dict[str, str]]]:
        models = [
            {
                "key": spec.key,
                "model_id": spec.model_id,
                "family": spec.family,
                "recommended_quantization": spec.recommended_quantization,
                "notes": spec.notes,
            }
            for spec in list_available_caption_models()
        ]
        return {"models": models}

    return app


app = create_app()
