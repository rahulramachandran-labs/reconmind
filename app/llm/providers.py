"""LLM access with a fallback chain: OpenAI, Anthropic, then the free tiers of Groq,
Gemini and OpenRouter, then local Ollama.

A provider that fails is benched for a cooldown so one outage doesn't add a
timeout to every request. ``DEMO_MODE`` removes the paid providers entirely.
If nothing answers, callers get ``LLMUnavailable`` and decide what to do; the
RAG path falls back to an extractive answer.
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from openai import OpenAI

from app.core.config import Settings

log = logging.getLogger(__name__)

# USD per million tokens (input, output). Local models and free tiers cost nothing,
# so the free-tier defaults below are deliberately not in this table.
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


class EmptyReply(RuntimeError):
    pass


class Provider(Protocol):
    name: str
    model: str

    def complete(self, system: str, messages: list[Message], max_tokens: int) -> Completion: ...


class OpenAICompatibleProvider:
    """OpenAI itself, or anything that speaks its chat API: Groq, Gemini, OpenRouter, and
    Ollama under /v1. Providers differ in what the token limit is called and in a few
    extra parameters, such as how much a reasoning model may think before answering."""

    def __init__(
        self,
        name: str,
        model: str,
        client: Any,
        *,
        limit_param: str = "max_completion_tokens",
        extra: dict[str, Any] | None = None,
        free: bool = False,
    ) -> None:
        self.name, self.model, self.client = name, model, client
        self.limit_param, self.extra = limit_param, extra or {}
        self.free = free or name == "ollama"  # a local model costs nothing

    def complete(self, system: str, messages: list[Message], max_tokens: int) -> Completion:
        start = time.perf_counter()
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}]
            + [{"role": m.role, "content": m.content} for m in messages],
            **{self.limit_param: max_tokens},
            **self.extra,
        )
        usage = resp.usage
        p_tok = usage.prompt_tokens if usage else 0
        c_tok = usage.completion_tokens if usage else 0
        text = (resp.choices[0].message.content or "").strip()
        if not text:
            # a reasoning model that spent its whole budget thinking; let the chain move on
            raise EmptyReply(f"{self.name} returned no text")
        return Completion(
            text=text,
            provider=self.name,
            model=self.model,
            latency_ms=int((time.perf_counter() - start) * 1000),
            prompt_tokens=p_tok,
            completion_tokens=c_tok,
            cost_usd=0.0 if self.free else estimate_cost(self.model, p_tok, c_tok),
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


def _openai_client(
    settings: Settings,
    api_key: str,
    base_url: str | None = None,
    *,
    max_retries: int = 1,
    headers: dict[str, str] | None = None,
) -> OpenAI:
    return OpenAI(
        api_key=api_key,
        base_url=base_url,
        timeout=settings.llm_timeout_s,
        max_retries=max_retries,
        default_headers=headers,
    )


# Free tiers answer 429 when a burst goes over the per-minute token limit; the client
# waits out the Retry-After and tries again before the chain gives up on the provider.
FREE_TIER_RETRIES = 3


def build_providers(settings: Settings) -> list[Provider]:
    providers: list[Provider] = []
    for name in settings.llm_providers:
        if name in ("openai", "anthropic") and settings.demo_mode:
            continue
        if name == "openai" and settings.openai_api_key:
            client = _openai_client(settings, settings.openai_api_key.get_secret_value())
            providers.append(OpenAICompatibleProvider("openai", settings.openai_model, client))
        elif name == "anthropic" and settings.anthropic_api_key:
            from anthropic import Anthropic

            anthropic_client = Anthropic(
                api_key=settings.anthropic_api_key.get_secret_value(),
                timeout=settings.llm_timeout_s,
                max_retries=1,
            )
            providers.append(AnthropicProvider(settings.anthropic_model, anthropic_client))
        elif name == "groq" and settings.groq_api_key:
            client = _openai_client(
                settings,
                settings.groq_api_key.get_secret_value(),
                settings.groq_base_url,
                max_retries=FREE_TIER_RETRIES,
            )
            # gpt-oss models reason before answering; keep that short so the JSON fits
            extra = {"reasoning_effort": "low"} if "gpt-oss" in settings.groq_model else {}
            providers.append(
                OpenAICompatibleProvider(
                    "groq", settings.groq_model, client, extra=extra, free=settings.groq_free_tier
                )
            )
        elif name == "gemini" and settings.gemini_api_key:
            client = _openai_client(
                settings,
                settings.gemini_api_key.get_secret_value(),
                settings.gemini_base_url,
                max_retries=FREE_TIER_RETRIES,
            )
            # 2.5 and later think by default, and the thinking counts against max_tokens
            thinks = not settings.gemini_model.startswith(("gemini-1", "gemini-2.0"))
            extra = {"reasoning_effort": "none"} if thinks else {}
            providers.append(
                OpenAICompatibleProvider(
                    "gemini",
                    settings.gemini_model,
                    client,
                    limit_param="max_tokens",
                    extra=extra,
                    free=settings.gemini_free_tier,
                )
            )
        elif name == "openrouter" and settings.openrouter_api_key:
            client = _openai_client(
                settings,
                settings.openrouter_api_key.get_secret_value(),
                settings.openrouter_base_url,
                max_retries=FREE_TIER_RETRIES,
                headers={"HTTP-Referer": settings.public_url, "X-Title": "ReconMind"},
            )
            providers.append(
                OpenAICompatibleProvider(
                    "openrouter",
                    settings.openrouter_model,
                    client,
                    limit_param="max_tokens",
                    free=settings.openrouter_model.endswith(":free"),
                )
            )
        elif name == "ollama" and settings.ollama_base_url:
            client = _openai_client(
                settings, "ollama", settings.ollama_base_url.rstrip("/") + "/v1", max_retries=0
            )
            providers.append(OpenAICompatibleProvider("ollama", settings.ollama_model, client))
    active = [p.name for p in providers]
    skipped = {
        name: (
            "DEMO_MODE"
            if settings.demo_mode and name in ("openai", "anthropic")
            else "no OLLAMA_BASE_URL" if name == "ollama" else f"no {name.upper()}_API_KEY"
        )
        for name in settings.llm_providers
        if name not in active
    }
    if active:
        log.info("model providers", extra={"active": active, "skipped": skipped})
    else:
        log.warning(
            "no model provider configured: answers will be extractive and write-ups templates",
            extra={"skipped": skipped},
        )
    return providers


@dataclass
class LastCall:
    provider: str
    model: str | None
    fell_back: bool
    at: datetime


class LLMChain:
    def __init__(
        self, providers: list[Provider], cooldown_s: float = 60.0, concurrency: int = 4
    ) -> None:
        self.providers = providers
        self.cooldown_s = cooldown_s
        self._benched_until: dict[str, float] = {}
        # a scan writes up findings in parallel; free tiers count tokens per minute
        self._slots = threading.BoundedSemaphore(max(1, concurrency))
        self.last: LastCall | None = None

    @classmethod
    def from_settings(cls, settings: Settings) -> "LLMChain":
        return cls(build_providers(settings), settings.llm_cooldown_s, settings.llm_concurrency)

    def status(self) -> dict[str, object]:
        """Which provider the next call goes to, and how the last one went."""
        now = time.monotonic()
        ready = [p for p in self.providers if self._benched_until.get(p.name, 0) <= now]
        active = ready[0] if ready else None
        return {
            "provider": active.name if active else "extractive",
            "model": active.model if active else None,
            "chain": self.names or ["extractive"],
            "models": {p.name: p.model for p in self.providers},
            "fell_back": self.last.fell_back if self.last else None,
            "last_provider": self.last.provider if self.last else None,
            "last_call_at": self.last.at.isoformat() if self.last else None,
        }

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
        with self._slots:
            return self._complete(system, messages, max_tokens)

    def _complete(self, system: str, messages: list[Message], max_tokens: int) -> Completion:
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
            self.last = LastCall(out.provider, out.model, bool(failed), datetime.now(UTC))
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
        if self.providers:
            self.last = LastCall("extractive", None, True, datetime.now(UTC))
        raise LLMUnavailable("no provider answered: " + (", ".join(failed) or "none configured"))
