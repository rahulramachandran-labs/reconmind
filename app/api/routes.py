from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app import __version__
from app.api.deps import get_app_settings, get_llm, get_retrieval, get_sessions
from app.api.guards import rate_limit
from app.config import Settings
from app.llm import LLMChain, Message
from app.rag import Answer, answer_question
from app.retrieval.service import RetrievalService
from app.retrieval.types import RetrievedChunk
from app.sessions import SessionFull, SessionStore

router = APIRouter()

Retrieval = Annotated[RetrievalService, Depends(get_retrieval)]
LLM = Annotated[LLMChain, Depends(get_llm)]
Sessions = Annotated[SessionStore, Depends(get_sessions)]
AppSettings = Annotated[Settings, Depends(get_app_settings)]


class AskRequest(BaseModel):
    question: str = Field(min_length=3)
    k: int = Field(default=5, ge=1, le=10)
    session_id: UUID | None = None


class AskResponse(Answer):
    session_id: UUID


class CorpusDoc(BaseModel):
    doc_id: str
    title: str
    path: str
    doc_type: str


class CorpusDocBody(CorpusDoc):
    body: str


class SessionMessage(BaseModel):
    role: str
    content: str
    created_at: datetime
    meta: dict[str, Any]


@router.get("/healthz")
def healthz(request: Request, retrieval: Retrieval, llm: LLM) -> dict[str, object]:
    return {
        "status": "ok",
        "version": __version__,
        "chunks": len(retrieval.chunks),
        "retriever": retrieval.mode,
        "llm_providers": llm.names or ["extractive"],
        "database": getattr(request.app.state, "db_ok", False),
    }


@router.post(
    "/ask", response_model=AskResponse, dependencies=[Depends(rate_limit("rate_limit_ask"))]
)
def ask(
    body: AskRequest,
    retrieval: Retrieval,
    llm: LLM,
    sessions: Sessions,
    settings: AppSettings,
) -> AskResponse:
    question = body.question.strip()
    if len(question) > settings.max_question_chars:
        raise HTTPException(413, f"question longer than {settings.max_question_chars} characters")
    if body.session_id and sessions.exists(body.session_id):
        session_id = body.session_id
    else:
        session_id = sessions.create(title=question)
    history = [
        Message(m.role, m.content)
        for m in sessions.history(session_id, limit=settings.history_turns * 2)
    ]
    answer = answer_question(question, retrieval, llm, k=body.k, history=history)
    try:
        sessions.append(session_id, "user", question)
        sessions.append(
            session_id,
            "assistant",
            answer.answer,
            {
                "provider": answer.provider,
                "model": answer.model,
                "sources": [s.chunk_id for s in answer.sources],
            },
        )
    except SessionFull as exc:
        raise HTTPException(409, "session is full, start a new one") from exc
    return AskResponse(**answer.model_dump(), session_id=session_id)


@router.get("/sessions/{session_id}/messages", response_model=list[SessionMessage])
def session_messages(session_id: UUID, sessions: Sessions) -> list[SessionMessage]:
    if not sessions.exists(session_id):
        raise HTTPException(404, "unknown session")
    return [
        SessionMessage(role=m.role, content=m.content, created_at=m.created_at, meta=m.meta)
        for m in sessions.history(session_id, limit=200)
    ]


@router.get("/search", response_model=list[RetrievedChunk])
def search(
    retrieval: Retrieval,
    q: Annotated[str, Query(min_length=2, max_length=500)],
    k: Annotated[int, Query(ge=1, le=20)] = 8,
    mode: Literal["hybrid", "dense", "bm25"] | None = None,
) -> list[RetrievedChunk]:
    return retrieval.search(q, k, mode=mode)


@router.get("/corpus", response_model=list[CorpusDoc])
def corpus(retrieval: Retrieval) -> list[CorpusDoc]:
    return [
        CorpusDoc(doc_id=d.doc_id, title=d.title, path=d.path, doc_type=d.doc_type)
        for d in retrieval.docs
    ]


@router.get("/corpus/{doc_id:path}", response_model=CorpusDocBody)
def corpus_doc(doc_id: str, retrieval: Retrieval) -> CorpusDocBody:
    doc = retrieval.document(doc_id)
    if doc is None:
        raise HTTPException(404, "unknown document")
    return CorpusDocBody(
        doc_id=doc.doc_id, title=doc.title, path=doc.path, doc_type=doc.doc_type, body=doc.body
    )
