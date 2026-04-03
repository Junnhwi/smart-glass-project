from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.api.errors import register_exception_handlers
from src.api.health import build_health_payload, build_liveness_payload
from src.api.middleware import RequestContextLoggingMiddleware
from src.api.schemas import (
    ChatRequest,
    ChatResponse,
    IndexMemoriesRequest,
    IndexMemoriesResponse,
    SearchHitPayload,
    SearchResponse,
    SearchRequest,
)
from src.core.logging import configure_logging, get_logger
from src.retriever.hybrid import SearchHit
from src.retriever.service import RagQueryService
from src.utils.config import get_settings


logger = get_logger(__name__)


def _map_hit(hit: SearchHit) -> SearchHitPayload:
    return SearchHitPayload(
        memory_id=hit.memory.memory_id,
        score=hit.score,
        lexical_score=hit.lexical_score,
        matched_terms=hit.matched_terms,
        image_key=hit.memory.image_key,
        image_url=hit.memory.image_url,
        captured_at=hit.memory.captured_at,
        caption=hit.memory.caption,
        scene_summary=hit.memory.scene_summary,
        position_hint=hit.memory.position_hint,
        location=hit.memory.location.to_dict(),
        detected_objects=hit.memory.detected_objects,
        tags=hit.memory.tags,
    )


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()
    rag_service = RagQueryService.from_settings(settings)

    app = FastAPI(
        title="smart-glass-rag-service",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.settings = settings
    app.state.rag_service = rag_service
    app.add_middleware(RequestContextLoggingMiddleware)
    register_exception_handlers(app)

    @app.get("/health/live")
    async def liveness_check() -> JSONResponse:
        status_code, payload = build_liveness_payload()
        return JSONResponse(status_code=status_code, content=payload)

    @app.get("/health/ready")
    async def readiness_check(request: Request) -> JSONResponse:
        status_code, payload = build_health_payload(
            request.app.state.settings,
            request.app.state.rag_service,
        )
        return JSONResponse(status_code=status_code, content=payload)

    @app.get("/health")
    async def health_check(request: Request) -> JSONResponse:
        status_code, payload = build_health_payload(
            request.app.state.settings,
            request.app.state.rag_service,
        )
        return JSONResponse(status_code=status_code, content=payload)

    @app.post("/memories/index", response_model=IndexMemoriesResponse)
    async def index_memories(
        request: Request, payload: IndexMemoriesRequest
    ) -> IndexMemoriesResponse:
        result = request.app.state.rag_service.index_memories(payload.memories)
        return IndexMemoriesResponse(**result)

    @app.post("/search", response_model=SearchResponse)
    async def search_memories(
        request: Request, payload: SearchRequest
    ) -> SearchResponse:
        hits = request.app.state.rag_service.search(
            user_id=payload.user_id,
            query=payload.query,
            top_k=payload.top_k,
        )
        return SearchResponse(
            query=payload.query,
            total_hits=len(hits),
            hits=[_map_hit(hit) for hit in hits],
        )

    @app.post("/chat", response_model=ChatResponse)
    async def chat_with_memories(
        request: Request, payload: ChatRequest
    ) -> ChatResponse:
        answer_result, hits = request.app.state.rag_service.chat(
            user_id=payload.user_id,
            query=payload.query,
            top_k=payload.top_k,
        )

        logger.info(
            "Generated chat answer",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "user_id": payload.user_id,
                "query": payload.query,
                "answer_mode": answer_result.mode,
            },
        )

        return ChatResponse(
            answer=answer_result.text,
            answer_mode=answer_result.mode,
            query=payload.query,
            total_hits=len(hits),
            hits=[_map_hit(hit) for hit in hits],
            cited_memory_ids=answer_result.cited_memory_ids or [],
            confidence=answer_result.confidence,
            reason=answer_result.reason,
        )

    return app


app = create_app()
