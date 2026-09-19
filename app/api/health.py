from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app import __version__
from app.api.deps import get_llm, get_retrieval
from app.llm.providers import LLMChain
from app.retrieval.service import RetrievalService

router = APIRouter()


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
        "database": getattr(request.app.state, "db_ok", False),
    }
