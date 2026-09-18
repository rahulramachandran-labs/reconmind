import logging
import time
from dataclasses import dataclass

from openai import OpenAI

from app.config import Settings

log = logging.getLogger(__name__)


@dataclass
class Completion:
    text: str
    provider: str
    model: str
    latency_ms: int
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMUnavailable(RuntimeError):
    pass


class LLMClient:
    """One OpenAI-compatible client. Ollama serves the same API under /v1."""

    def __init__(self, settings: Settings, client: OpenAI | None = None) -> None:
        self.provider = settings.llm_provider
        if self.provider == "openai":
            key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
            self.model = settings.openai_model
            self._client = client or (
                OpenAI(api_key=key, timeout=settings.llm_timeout_s) if key else None
            )
        elif self.provider == "ollama":
            self.model = settings.ollama_model
            self._client = client or OpenAI(
                base_url=settings.ollama_base_url.rstrip("/") + "/v1",
                api_key="ollama",
                timeout=settings.llm_timeout_s,
                max_retries=0,
            )
        else:
            self.model = ""
            self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def complete(self, system: str, user: str, max_tokens: int = 600) -> Completion:
        if self._client is None:
            raise LLMUnavailable(f"no client configured for provider={self.provider}")
        start = time.perf_counter()
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                max_completion_tokens=max_tokens,
            )
        except Exception as exc:
            raise LLMUnavailable(f"{self.provider} call failed: {exc}") from exc
        usage = resp.usage
        return Completion(
            text=(resp.choices[0].message.content or "").strip(),
            provider=self.provider,
            model=self.model,
            latency_ms=int((time.perf_counter() - start) * 1000),
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )
