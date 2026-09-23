"""Three probes, on purpose.

``/livez`` says the process is up and touches nothing else, so a database blip
can't get a free instance restart-looped. ``/readyz`` says every dependency this
process needs is answering, and names the ones that are not. ``/healthz`` is the
shape the web app and the workflows already read, kept as it was.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response

from app import __version__
from app.api.deps import get_llm, get_retrieval
from app.llm.providers import LLMChain
from app.retrieval.service import RetrievalService

router = APIRouter()
log = logging.getLogger("reconmind")


@router.get("/livez")
def livez() -> dict[str, str]:
    return {"status": "alive", "version": __version__}


@router.get("/healthz")
def healthz(
    request: Request,
    retrieval: Annotated[RetrievalService, Depends(get_retrieval)],
    llm: Annotated[LLMChain, Depends(get_llm)],
) -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        "chunks": len(retrieval.chunks),
        "retriever": retrieval.mode,
        "llm_providers": llm.names or ["extractive"],
        "llm_models": {p.name: p.model for p in llm.providers},
        "database": getattr(request.app.state, "db_ok", False),
    }


@router.get("/readyz")
async def readyz(
    request: Request,
    response: Response,
    retrieval: Annotated[RetrievalService, Depends(get_retrieval)],
    llm: Annotated[LLMChain, Depends(get_llm)],
) -> dict[str, Any]:
    checks: dict[str, Any] = {
        "index": _index(retrieval),
        "database": _database(request),
        "models": _models(llm),
        "tools": await _tools(request),
    }
    ready = all(c["ok"] for c in checks.values())
    response.status_code = 200 if ready else 503
    return {
        "status": "ready" if ready else "degraded",
        "version": __version__,
        "checks": checks,
        "failing": sorted(name for name, c in checks.items() if not c["ok"]),
    }


def _index(retrieval: RetrievalService) -> dict[str, Any]:
    chunks = len(retrieval.chunks)
    return {"ok": chunks > 0, "chunks": chunks, "retriever": retrieval.mode}


def _database(request: Request) -> dict[str, Any]:
    """Configured but unreachable is a failure; not configured at all is a choice."""
    settings = request.app.state.settings
    if not settings.database_url:
        return {"ok": True, "detail": "not configured; runs and chat are in memory"}
    from app.db.session import get_engine, ping

    try:
        reachable = ping(get_engine(settings.database_url))
    except Exception as exc:
        return {"ok": False, "detail": str(exc)[:200]}
    return {"ok": reachable, "detail": "one-row query" if reachable else "unreachable"}


def _models(llm: LLMChain) -> dict[str, Any]:
    status = llm.status()
    benched = llm.benched()
    return {
        # no provider at all is fine: the answers are extractive and say so
        "ok": True,
        "active": status["provider"],
        "chain": status["chain"],
        "cooling_down": benched,
    }


async def _tools(request: Request) -> dict[str, Any]:
    investigations = getattr(request.app.state, "investigations", None)
    if investigations is None:
        return {"ok": True, "detail": "agents are off"}
    try:
        tools = await investigations.deps.tools.list_tools()
    except Exception as exc:
        return {"ok": False, "detail": str(exc)[:200]}
    missing = sorted(server for server, names in tools.items() if not names)
    return {
        "ok": not missing and bool(tools),
        "servers": {server: len(names) for server, names in tools.items()},
        "silent": missing,
    }


@router.get("/model")
def model(llm: Annotated[LLMChain, Depends(get_llm)]) -> dict[str, object]:
    """The provider the next model call goes to, and whether the last one fell back."""
    return llm.status()
