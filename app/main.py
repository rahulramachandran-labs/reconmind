import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.agents import router as agents_router
from app.api.dashboard import router as dashboard_router
from app.api.guards import RateLimiter
from app.api.routes import router
from app.config import Settings, get_settings
from app.llm import LLMChain
from app.logging_setup import configure_logging
from app.retrieval.service import RetrievalService
from app.sessions import MemorySessionStore, SessionStore, SqlSessionStore

log = logging.getLogger("reconmind")


def build_session_store(settings: Settings) -> tuple[SessionStore, bool]:
    if settings.database_url:
        from app.db.session import get_engine, ping

        engine = get_engine(settings.database_url)
        if ping(engine):
            return SqlSessionStore(engine), True
        log.warning("database unreachable, keeping chat sessions in memory")
    return MemorySessionStore(), False


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.rate_limiter = RateLimiter()
        app.state.llm = LLMChain.from_settings(settings)
        app.state.retrieval = RetrievalService.from_settings(settings)
        app.state.sessions, app.state.db_ok = build_session_store(settings)
        stack = AsyncExitStack()
        app.state.investigations = None
        if settings.agents_enabled:
            from app.agents.bootstrap import build_investigations
            from app.db.session import get_engine

            engine = get_engine(settings.database_url) if app.state.db_ok else None
            try:
                app.state.investigations = await build_investigations(
                    settings, stack, app.state.retrieval, app.state.llm, engine
                )
            except Exception:
                log.exception("agents failed to start; serving retrieval only")
        log.info(
            "startup complete",
            extra={
                "chunks": len(app.state.retrieval.chunks),
                "providers": app.state.llm.names,
                "database": app.state.db_ok,
                "agents": app.state.investigations is not None,
            },
        )
        scheduler = None
        if app.state.investigations is not None:
            from app.scheduler import start_scheduler

            scheduler = start_scheduler(app.state.investigations, settings.scan_interval_minutes)
        try:
            yield
        finally:
            if scheduler is not None:
                scheduler.shutdown(wait=False)
            await stack.aclose()

    app = FastAPI(
        title="ReconMind API",
        description="Multi-agent, RAG-powered incident copilot for data pipelines.",
        version=__version__,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
        expose_headers=["Retry-After"],
    )
    app.include_router(router)
    app.include_router(agents_router)
    app.include_router(dashboard_router)
    return app


app = create_app()
