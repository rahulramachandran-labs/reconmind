import asyncio
import json
import time
from typing import Any

from app.llm.providers import Completion, LLMChain, LLMUnavailable, Message, ToolTurn
from app.observability.tracer import Step, current_tracer


class UntracedCall(RuntimeError):
    pass


class TracedLLM:
    """The only way agents talk to a model. Every attempt becomes a trace step."""

    def __init__(self, chain: LLMChain) -> None:
        self.chain = chain

    @property
    def enabled(self) -> bool:
        return self.chain.enabled

    async def complete(
        self,
        system: str,
        messages: list[Message],
        *,
        name: str,
        prompt_version: str,
        max_tokens: int = 700,
        json_object: bool = False,
        steps: list[Step] | None = None,
    ) -> Completion:
        """``json_object`` asks providers that support it to answer with JSON and nothing
        else. ``steps`` collects the trace step of each call, so a caller that validates the
        reply can write why it failed onto the step that produced it."""
        tracer = current_tracer()
        if tracer is None:
            raise UntracedCall(f"LLM call '{name}' outside a traced run")
        start = time.perf_counter()
        preview = {
            "system": system[:1500],
            "messages": [{"role": m.role, "content": m.content[:3000]} for m in messages],
        }
        try:
            out = await asyncio.to_thread(
                self.chain.complete, system, messages, max_tokens, json_object
            )
        except LLMUnavailable as exc:
            tracer.record(
                kind="llm",
                name=name,
                prompt_version=prompt_version,
                input=preview,
                latency_ms=int((time.perf_counter() - start) * 1000),
                error=str(exc)[:500],
            )
            raise
        step = tracer.record(
            kind="llm",
            name=name,
            provider=out.provider,
            model=out.model,
            prompt_version=prompt_version,
            input=preview,
            output={
                "text": out.text[:4000],
                "finish_reason": out.finish_reason,
                "fallbacks": out.fallbacks,
            },
            prompt_tokens=out.prompt_tokens,
            completion_tokens=out.completion_tokens,
            cost_usd=out.cost_usd,
            latency_ms=out.latency_ms,
        )
        if steps is not None:
            steps.append(step)
        return out

    async def complete_tools(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        name: str,
        prompt_version: str,
        max_tokens: int = 900,
    ) -> ToolTurn:
        """One turn of a tool-calling conversation, traced like any other model call; the
        tools it asks for are recorded in the step's output."""
        tracer = current_tracer()
        if tracer is None:
            raise UntracedCall(f"LLM call '{name}' outside a traced run")
        start = time.perf_counter()
        preview = {
            "system": system[:1500],
            "messages": [json.dumps(m, default=str)[:1500] for m in messages[-6:]],
            "tools": [t["function"]["name"] for t in tools],
        }
        try:
            out = await asyncio.to_thread(
                self.chain.complete_tools, system, messages, tools, max_tokens
            )
        except LLMUnavailable as exc:
            tracer.record(
                kind="llm",
                name=name,
                prompt_version=prompt_version,
                input=preview,
                latency_ms=int((time.perf_counter() - start) * 1000),
                error=str(exc)[:500],
            )
            raise
        tracer.record(
            kind="llm",
            name=name,
            provider=out.provider,
            model=out.model,
            prompt_version=prompt_version,
            input=preview,
            output={
                "text": out.text[:4000],
                "finish_reason": out.finish_reason,
                "tool_calls": [{"name": c.name, "arguments": c.arguments} for c in out.tool_calls],
                "fallbacks": out.fallbacks,
            },
            prompt_tokens=out.prompt_tokens,
            completion_tokens=out.completion_tokens,
            cost_usd=out.cost_usd,
            latency_ms=out.latency_ms,
        )
        return out
