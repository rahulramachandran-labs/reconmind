import asyncio
import time

from app.llm import Completion, LLMChain, LLMUnavailable, Message
from app.observability.tracer import current_tracer


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
    ) -> Completion:
        tracer = current_tracer()
        if tracer is None:
            raise UntracedCall(f"LLM call '{name}' outside a traced run")
        start = time.perf_counter()
        preview = {
            "system": system[:1500],
            "messages": [{"role": m.role, "content": m.content[:3000]} for m in messages],
        }
        try:
            out = await asyncio.to_thread(self.chain.complete, system, messages, max_tokens)
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
            output={"text": out.text[:4000], "fallbacks": out.fallbacks},
            prompt_tokens=out.prompt_tokens,
            completion_tokens=out.completion_tokens,
            cost_usd=out.cost_usd,
            latency_ms=out.latency_ms,
        )
        return out
