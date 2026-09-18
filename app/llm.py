"""LLM access with a fallback chain: OpenAI, then Anthropic, then local Ollama.

A provider that fails is benched for a cooldown so one outage doesn't add a
timeout to every request. ``DEMO_MODE`` removes the paid providers entirely.
If nothing answers, callers get ``LLMUnavailable`` and decide what to do; the
RAG path falls back to an extractive answer.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from openai import OpenAI

from app.config import Settings

log = logging.getLogger(__name__)

# USD per million tokens (input, output). Local models cost nothing.
PRICES: dict[str, tuple[float, float]] = {
    "gpt-5-mini": (0.25, 2.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-sonnet-5": (3.00, 15.00),
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    return round((prompt_tokens * price_in + completion_tokens * price_out) / 1_000_000, 6)


@dataclass
class Message:
    role: str
    content: str


@dataclass
class Completion:
    text: str
    provider: str
    model: str
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    fallbacks: list[str] = field(default_factory=list)


class LLMUnavailable(RuntimeError):
    pass


class Provider(Protocol):
    name: str
    model: str

    def complete(self, system: str, messages: list[Message], max_tokens: int) -> Completion: ...


class OpenAICompatibleProvider:
    """OpenAI itself, or anything that speaks its chat API (Ollama serves it under /v1)."""

    def __init__(self, name: str, model: str, client: Any) -> None:
        self.name, self.model, self.client = name, model, client

    def complete(self, system: str, messages: list[Message], max_tokens: int) -> Completion:
        start = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
            max_completion_tokens=max_tokens,
        )
        usage = resp.usage
        p_tok = usage.prompt_tokens if usage else 0
        c_tok = usage.completion_tokens if usage else 0
        return Completion(
            text=(resp.choices[0].message.content or "").strip(),
            provider=self.name,
            model=self.model,
            latency_ms=int((time.perf_counter() - start) * 1000),
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
            cost_usd=estimate_cost(self.model, p_tok, c_tok) if self.name != "ollama" else 0.0,
        )


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, model: str, client: Any) -> None:
        self.model, self.client = model, client

    def complete(self, system: str, messages: list[Message], max_tokens: int) -> Completion:
        start = time.perf_counter()
        resp = self.client.messages.create(
            model=self.model,
            system=system,
            max_tokens=max_tokens,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        p_tok, c_tok = resp.usage.input_tokens, resp.usage.output_tokens
        return Completion(
            text=text.strip(),
            provider=self.name,
            model=self.model,
            latency_ms=int((time.perf_counter() - start) * 1000),
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
            cost_usd=estimate_cost(self.model, p_tok, c_tok),
        )


def build_providers(settings: Settings) -> list[Provider]:
    providers: list[Provider] = []
    for name in settings.llm_providers:
        if name in ("openai", "anthropic") and settings.demo_mode:
            continue
        if name == "openai" and settings.openai_api_key:
            client = OpenAI(
                api_key=settings.openai_api_key.get_secret_value(),
                timeout=settings.llm_timeout_s,
                max_retries=1,
            )
            providers.append(OpenAICompatibleProvider("openai", settings.openai_model, client))
        elif name == "anthropic" and settings.anthropic_api_key:
            from anthropic import Anthropic

            anthropic_client = Anthropic(
                api_key=settings.anthropic_api_key.get_secret_value(),
                timeout=settings.llm_timeout_s,
                max_retries=1,
            )
            providers.append(AnthropicProvider(settings.anthropic_model, anthropic_client))
        elif name == "ollama" and settings.ollama_base_url:
            client = OpenAI(
                base_url=settings.ollama_base_url.rstrip("/") + "/v1",
                api_key="ollama",
                timeout=settings.llm_timeout_s,
                max_retries=0,
            )
            providers.append(OpenAICompatibleProvider("ollama", settings.ollama_model, client))
    return providers


class LLMChain:
    def __init__(self, providers: list[Provider], cooldown_s: float = 60.0) -> None:
        self.providers = providers
        self.cooldown_s = cooldown_s
        self._benched_until: dict[str, float] = {}

    @classmethod
    def from_settings(cls, settings: Settings) -> "LLMChain":
        return cls(build_providers(settings), settings.llm_cooldown_s)

    @property
    def enabled(self) -> bool:
        return bool(self.providers)

    @property
    def names(self) -> list[str]:
        return [p.name for p in self.providers]

    def complete(
        self,
        system: str,
        user: str | list[Message],
        max_tokens: int = 700,
    ) -> Completion:
        messages = [Message("user", user)] if isinstance(user, str) else user
        failed: list[str] = []
        now = time.monotonic()
        for p in self.providers:
            if self._benched_until.get(p.name, 0) > now:
                failed.append(f"{p.name}:cooldown")
                continue
            try:
                out = p.complete(system, messages, max_tokens)
            except Exception as exc:
                self._benched_until[p.name] = time.monotonic() + self.cooldown_s
                failed.append(f"{p.name}:{type(exc).__name__}")
                log.warning("provider failed", extra={"provider": p.name, "error": str(exc)[:200]})
                continue
            out.fallbacks = failed
            log.info(
                "llm call",
                extra={
                    "provider": out.provider,
                    "model": out.model,
                    "latency_ms": out.latency_ms,
                    "tokens": out.prompt_tokens + out.completion_tokens,
                    "fallbacks": failed,
                },
            )
            return out
        raise LLMUnavailable("no provider answered: " + (", ".join(failed) or "none configured"))
