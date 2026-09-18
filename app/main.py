import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import router
from app.config import Settings, get_settings
from app.llm import LLMClient
from app.logging_setup import configure_logging
from app.retrieval.service import RetrievalService

log = logging.getLogger("reconmind")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = settings
        app.state.retrieval = RetrievalService.from_settings(settings)
        app.state.llm = LLMClient(settings)
        log.info(
            "startup complete",
            extra={"chunks": len(app.state.retrieval.chunks), "llm": settings.llm_provider},
        )
        yield

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
    )
    app.include_router(router)
    return app


app = create_app()
