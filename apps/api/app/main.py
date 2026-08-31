from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .core.config import Settings, load_settings
from .core.logging import configure_logging
from .core.network import install_closed_network_guard
from .db.session import Database
from .repositories.store import ResearchRepository
from .services.factory import create_orchestrator


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    if settings.is_closed and settings.closed_test_block_network:
        install_closed_network_guard()
    configure_logging()
    db = Database(settings)
    if settings.bootstrap_schema_on_startup:
        db.create_schema()
    app = FastAPI(title="YouTube Niche Intelligence Engine", version="0.1.0")
    app.state.settings = settings
    app.state.db = db
    app.state.orchestrator = create_orchestrator(
        settings,
        ResearchRepository(db.session()),
        owns_runtime_storage=settings.is_closed,
    )
    if settings.is_closed:
        # Closed runs execute in-process. Every queued runtime delegates this
        # lifecycle operation to the mounted ARQ worker.
        app.state.orchestrator.artifacts.cleanup_expired()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_origin_regex=settings.cors_allowed_origin_regex,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Link", "X-Total-Count", "X-Pagination-Limit", "X-Pagination-Offset"],
    )
    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": settings.app_mode.value}

    @app.on_event("shutdown")
    def close_resources() -> None:
        app.state.orchestrator.repository.session.close()
        db.engine.dispose()

    return app


app = create_app()
