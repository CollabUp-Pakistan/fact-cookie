"""FastAPI application entrypoint for Fact Cookie."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastmcp.utilities.lifespan import combine_lifespans

from app.api.auth import api_keys_router, router as auth_router
from app.api.billing import router as billing_router
from app.api.documents import router as documents_router
from app.api.insights import router as insights_router
from app.api.oauth import router as oauth_router
from app.api.preferences import router as preferences_router
from app.api.usage import router as usage_router
from app.api.verifications import jobs_router, router as verifications_router
from app.core.config import settings
from app.core.errors import install_exception_handlers
from app.core.logging import configure_logging, get_logger, request_id_ctx
from app.db.session import engine, session_factory
from app.db.base import Base
from app.mcp.server import mcp_app
from app.services import plan_service

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    settings.ensure_directories()
    async with session_factory() as db:
        await plan_service.seed_plans(db)
    logger.info("startup", extra={"extra_fields": {"app": settings.app_name, "env": settings.environment}})
    yield
    await engine.dispose()
    logger.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=combine_lifespans(lifespan, mcp_app.lifespan),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.effective_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or __import__("uuid").uuid4().hex
        token = request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
            response.headers["x-request-id"] = request_id
            return response
        finally:
            request_id_ctx.reset(token)

    install_exception_handlers(app)

    app.include_router(auth_router, prefix=settings.api_v1_prefix)
    app.include_router(api_keys_router, prefix=settings.api_v1_prefix)
    app.include_router(billing_router, prefix=settings.api_v1_prefix)
    app.include_router(usage_router, prefix=settings.api_v1_prefix)
    app.include_router(documents_router, prefix=settings.api_v1_prefix)
    app.include_router(preferences_router, prefix=settings.api_v1_prefix)
    app.include_router(verifications_router, prefix=settings.api_v1_prefix)
    app.include_router(jobs_router, prefix=settings.api_v1_prefix)
    app.include_router(insights_router, prefix=settings.api_v1_prefix)
    app.include_router(oauth_router)
    app.mount("/mcp/", mcp_app)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    @app.get("/api/v1/health", tags=["health"])
    async def api_health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    return app


app = create_app()
