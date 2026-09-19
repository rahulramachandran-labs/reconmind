"""Answer node: when the Planner decides the runbooks alone can answer, reply
from retrieved passages with citations, no investigation."""

from typing import Any

from app.agents.deps import AgentDeps, traced_search
from app.llm.providers import LLMUnavailable, Message
from app.rag.extractive import extractive_answer
from app.rag.prompts import (
    ANSWER_PROMPT_VERSION,
    ANSWER_SYSTEM_PROMPT,
    format_passages,
    retrieval_query,
)


async def run(deps: AgentDeps, state: dict[str, Any]) -> dict[str, Any]:
    question = state.get("question") or ""
    history = [Message(m["role"], m["content"]) for m in state.get("history", [])]
    query = retrieval_query(question, history)
    chunks = traced_search(deps.retrieval, query, 5)
    text, provider = extractive_answer(question, chunks), "extractive"
    if deps.llm.enabled:
        turn = Message("user", f"{format_passages(chunks)}\n\nQuestion: {question}")
        try:
            out = await deps.llm.complete(
                ANSWER_SYSTEM_PROMPT,
                [*history, turn],
                name="answer",
                prompt_version=ANSWER_PROMPT_VERSION,
            )
            text, provider = out.text, out.provider
        except LLMUnavailable:
            pass
    return {
        "answer": text,
        "answer_provider": provider,
        "sources": [c.model_dump(exclude={"text"}) for c in chunks],
    }
