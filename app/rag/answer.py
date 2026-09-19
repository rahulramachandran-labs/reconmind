"""Answer a question from the runbooks: retrieve, then generate with citations.

This is the path without agents (``POST /ask``). If no model answers, the
reply is built extractively from the same passages.
"""

import logging
import time

from pydantic import BaseModel, Field

from app.llm.providers import LLMChain, LLMUnavailable, Message
from app.rag.extractive import extractive_answer
from app.rag.prompts import (
    ANSWER_PROMPT_VERSION,
    ANSWER_SYSTEM_PROMPT,
    format_passages,
    retrieval_query,
)
from app.retrieval.service import RetrievalService
from app.retrieval.types import RetrievedChunk

log = logging.getLogger(__name__)


class Answer(BaseModel):
    answer: str
    sources: list[RetrievedChunk]
    provider: str
    model: str
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    fallbacks: list[str] = Field(default_factory=list)
    retrieval_query: str = ""
    prompt_version: str = ANSWER_PROMPT_VERSION


def answer_question(
    question: str,
    retrieval: RetrievalService,
    llm: LLMChain,
    k: int = 5,
    history: list[Message] | None = None,
) -> Answer:
    start = time.perf_counter()
    history = history or []
    query = retrieval_query(question, history)
    chunks = retrieval.search(query, k)
    fallbacks: list[str] = []
    if llm.enabled:
        try:
            turn = Message("user", f"{format_passages(chunks)}\n\nQuestion: {question}")
            out = llm.complete(ANSWER_SYSTEM_PROMPT, [*history, turn])
            return Answer(
                answer=out.text,
                sources=chunks,
                provider=out.provider,
                model=out.model,
                latency_ms=int((time.perf_counter() - start) * 1000),
                prompt_tokens=out.prompt_tokens,
                completion_tokens=out.completion_tokens,
                cost_usd=out.cost_usd,
                fallbacks=out.fallbacks,
                retrieval_query=query,
            )
        except LLMUnavailable as exc:
            log.warning("llm unavailable, answering extractively", extra={"error": str(exc)})
            fallbacks = str(exc).removeprefix("no provider answered: ").split(", ")
    return Answer(
        answer=extractive_answer(question, chunks),
        sources=chunks,
        provider="extractive",
        model="none",
        latency_ms=int((time.perf_counter() - start) * 1000),
        fallbacks=fallbacks,
        retrieval_query=query,
    )
