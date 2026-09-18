from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app import __version__
from app.api.deps import get_app_settings, get_llm, get_retrieval
from app.config import Settings
from app.llm import LLMClient
from app.rag import Answer, answer_question
from app.retrieval.service import RetrievalService
from app.retrieval.types import RetrievedChunk

router = APIRouter()

Retrieval = Annotated[RetrievalService, Depends(get_retrieval)]
LLM = Annotated[LLMClient, Depends(get_llm)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]


class AskRequest(BaseModel):
    question: str = Field(min_length=3)
    k: int = Field(default=5, ge=1, le=10)


class CorpusDoc(BaseModel):
    doc_id: str
    title: str
    path: str
    doc_type: str


@router.get("/healthz")
def healthz(retrieval: Retrieval, llm: LLM) -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        "chunks": len(retrieval.chunks),
        "llm_provider": llm.provider if llm.enabled else "extractive",
    }


@router.post("/ask", response_model=Answer)
def ask(body: AskRequest, retrieval: Retrieval, llm: LLM, settings: AppSettings) -> Answer:
    if len(body.question) > settings.max_question_chars:
        raise HTTPException(413, f"question longer than {settings.max_question_chars} characters")
    return answer_question(body.question.strip(), retrieval, llm, k=body.k)


@router.get("/search", response_model=list[RetrievedChunk])
def search(
    retrieval: Retrieval,
    q: Annotated[str, Query(min_length=2, max_length=500)],
    k: Annotated[int, Query(ge=1, le=20)] = 8,
) -> list[RetrievedChunk]:
    return retrieval.search(q, k)


@router.get("/corpus", response_model=list[CorpusDoc])
def corpus(retrieval: Retrieval) -> list[CorpusDoc]:
    return [
        CorpusDoc(doc_id=d.doc_id, title=d.title, path=d.path, doc_type=d.doc_type)
        for d in retrieval.docs
    ]
