"""FastAPI application factory for Stupid Code (Phase 3).

Importing this module builds the app but opens no database and builds no LLM_Router;
the shared engines are created lazily on first use (``services.get_services``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.errors import CatchAllMiddleware, install_exception_handlers
from backend.api.rate_limit import RateLimiter
from backend.api.routes import autopsy, crew, mastery, repos
from backend.api.services import Services
from backend.api.settings import ApiSettings, load_api_settings


def create_app(
    settings: ApiSettings | None = None,
    *,
    services: Services | None = None,
    rate_limiter: RateLimiter | None = None,
) -> FastAPI:
    """Build the application. A ``ConfigurationError`` from the settings propagates."""
    resolved = settings if settings is not None else load_api_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            created = getattr(app.state, "services_created_by_app", False)
            current = getattr(app.state, "services", None)
            if created and current is not None:
                current.cache.close()

    app = FastAPI(title="Stupid Code", lifespan=lifespan)
    app.state.api_settings = resolved
    app.state.rate_limiter = (
        rate_limiter
        if rate_limiter is not None
        else RateLimiter(resolved.github_rate_limit, resolved.github_rate_window_seconds)
    )
    app.state.services_created_by_app = False
    if services is not None:
        app.state.services = services

    # The last middleware added is the outermost: CORS wraps the catch-all so that
    # preflight requests and 500 envelopes both carry the CORS headers.
    app.add_middleware(CatchAllMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Kiro-Signature", "X-Crew-Proxy"],
    )
    install_exception_handlers(app)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "stupid-code"}

    # ``/api/repos/ingest`` (POST) has two segments after ``/api``; every
    # ``/api/repos/{repo_id}/...`` route has three or more, so none shadows it.
    app.include_router(repos.router)
    app.include_router(autopsy.router)
    app.include_router(mastery.router)
    app.include_router(crew.router)
    return app


app = create_app()
