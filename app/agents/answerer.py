"""Answer node: when the Planner decides the runbooks alone can answer, reply
from retrieved passages with citations, no investigation."""

from typing import Any

from app.agents.deps import AgentDeps, traced_search
from app.llm.providers import LLMUnavailable, Message
from app.rag.extractive import extractive_answer
from app.rag.prompts import ANSWER_PROMPT_VERSION, answer_messages, retrieval_query


async def run(deps: AgentDeps, state: dict[str, Any]) -> dict[str, Any]:
    question = state.get("question") or ""
    history = [Message(m["role"], m["content"]) for m in state.get("history", [])]
    query = retrieval_query(question, history)
    chunks = traced_search(deps.retrieval, query, 5)
    text, provider, model = extractive_answer(question, chunks), "extractive", None
    fallbacks: list[str] = []
    if deps.llm.enabled:
        system, turns = answer_messages(question, chunks, history)
        try:
            out = await deps.llm.complete(
                system,
                turns,
                name="answer",
                prompt_version=ANSWER_PROMPT_VERSION,
            )
            text, provider, model, fallbacks = out.text, out.provider, out.model, out.fallbacks
        except LLMUnavailable as exc:
            fallbacks = str(exc).removeprefix("no provider answered: ").split(", ")
    return {
        "answer": text,
        "answer_provider": provider,
        "answer_model": model,
        "answer_fallbacks": fallbacks,
        "sources": [c.model_dump(exclude={"text"}) for c in chunks],
    }
