import json
import time
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.llm import providers as providers_module
from app.llm.providers import (
    AnthropicProvider,
    Completion,
    LLMChain,
    LLMUnavailable,
    Message,
    OpenAICompatibleProvider,
    build_providers,
    estimate_cost,
)


class Scripted:
    def __init__(self, name: str, fail: bool = False) -> None:
        self.name, self.model, self.fail, self.calls = name, f"{name}-model", fail, 0

    def complete(
        self, system: str, messages: list[Message], max_tokens: int, json_object: bool = False
    ) -> Completion:
        self.calls += 1
        if self.fail:
            raise ConnectionError("down")
        return Completion(
            text=f"from {self.name}", provider=self.name, model=self.model, latency_ms=1
        )


def test_first_healthy_provider_answers_and_failures_are_recorded() -> None:
    a, b, c = Scripted("openai", fail=True), Scripted("anthropic"), Scripted("ollama")
    out = LLMChain([a, b, c]).complete("sys", "hi")
    assert out.provider == "anthropic"
    assert out.fallbacks == ["openai:ConnectionError"]
    assert c.calls == 0


def test_failed_provider_is_benched_for_the_cooldown() -> None:
    a, b = Scripted("openai", fail=True), Scripted("ollama")
    chain = LLMChain([a, b], cooldown_s=60)
    chain.complete("s", "u")
    out = chain.complete("s", "u")
    assert a.calls == 1
    assert out.fallbacks == ["openai:cooldown"]


def test_cooldown_expires() -> None:
    a, b = Scripted("openai", fail=True), Scripted("ollama")
    chain = LLMChain([a, b], cooldown_s=0.01)
    chain.complete("s", "u")
    time.sleep(0.02)
    chain.complete("s", "u")
    assert a.calls == 2


def test_everything_down_raises() -> None:
    with pytest.raises(LLMUnavailable, match="openai:ConnectionError"):
        LLMChain([Scripted("openai", fail=True)]).complete("s", "u")
    with pytest.raises(LLMUnavailable, match="none configured"):
        LLMChain([]).complete("s", "u")


def test_demo_mode_drops_paid_providers() -> None:
    s = Settings(
        _env_file=None,
        demo_mode=True,
        openai_api_key=SecretStr("sk-x"),
        anthropic_api_key=SecretStr("sk-ant-x"),
        llm_providers=["openai", "anthropic", "ollama"],
    )
    assert [p.name for p in build_providers(s)] == ["ollama"]


def test_providers_without_keys_are_skipped_and_order_is_kept() -> None:
    s = Settings(
        _env_file=None,
        openai_api_key=SecretStr("sk-x"),
        anthropic_api_key=SecretStr("sk-ant-x"),
        llm_providers=["anthropic", "openai", "ollama"],
    )
    assert [p.name for p in build_providers(s)] == ["anthropic", "openai", "ollama"]
    bare = Settings(_env_file=None, openai_api_key=None, anthropic_api_key=None, ollama_base_url="")
    assert build_providers(bare) == []


def test_openai_compatible_provider_maps_usage_and_cost() -> None:
    def create(**kw: Any) -> Any:
        assert kw["messages"][0]["role"] == "system"
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=" ok "))],
            usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=500),
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    out = OpenAICompatibleProvider("openai", "gpt-5-mini", client).complete(
        "s", [Message("user", "u")], 100
    )
    assert out.text == "ok" and out.cost_usd == estimate_cost("gpt-5-mini", 1000, 500) > 0
    local = OpenAICompatibleProvider("ollama", "gpt-5-mini", client).complete(
        "s", [Message("user", "u")], 100
    )
    assert local.cost_usd == 0.0


def test_anthropic_provider_joins_text_blocks() -> None:
    def create(**kw: Any) -> Any:
        assert kw["system"] == "s"
        return SimpleNamespace(
            content=[
                SimpleNamespace(type="text", text="a "),
                SimpleNamespace(type="tool_use"),
                SimpleNamespace(type="text", text="b"),
            ],
            usage=SimpleNamespace(input_tokens=10, output_tokens=5),
        )

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    out = AnthropicProvider("claude-haiku-4-5", client).complete("s", [Message("user", "u")], 50)
    assert out.text == "a b" and out.provider == "anthropic" and out.prompt_tokens == 10


def test_unknown_model_costs_nothing() -> None:
    assert estimate_cost("some-local-model", 10_000, 10_000) == 0.0


# -- free tiers over the OpenAI-compatible API, against mocked endpoints ------------


Handler = Callable[[httpx.Request], httpx.Response]


def _mocked(
    provider: str, reply: str = '{"ok": true}', status: int = 200
) -> tuple[Settings, list[httpx.Request], Handler]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "nope"}})
        return httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "created": 0,
                "model": "m",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": reply},
                    }
                ],
                "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
            },
        )

    settings = Settings(
        _env_file=None,
        llm_providers=[provider],
        ollama_base_url="",
        **{f"{provider}_api_key": SecretStr("k")},
    )
    return settings, seen, handler


@pytest.mark.parametrize(
    ("provider", "host", "path", "model", "limit_param", "extra"),
    [
        (
            "groq",
            "api.groq.com",
            "/openai/v1/chat/completions",
            "openai/gpt-oss-120b",
            "max_completion_tokens",
            {"reasoning_effort": "low"},
        ),
        (
            "gemini",
            "generativelanguage.googleapis.com",
            "/v1beta/openai/chat/completions",
            "gemini-3.6-flash",
            "max_tokens",
            {"reasoning_effort": "none"},
        ),
        (
            "openrouter",
            "openrouter.ai",
            "/api/v1/chat/completions",
            "deepseek/deepseek-v4-flash-0731:free",
            "max_tokens",
            {},
        ),
    ],
)
def test_free_tier_provider_calls_its_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    host: str,
    path: str,
    model: str,
    limit_param: str,
    extra: dict[str, str],
) -> None:
    settings, seen, handler = _mocked(provider)
    real = providers_module.OpenAI

    def with_transport(**kw: Any) -> Any:
        return real(**kw, http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    monkeypatch.setattr(providers_module, "OpenAI", with_transport)
    chain = LLMChain.from_settings(settings)
    assert chain.names == [provider]
    out = chain.complete("sys", "hello", max_tokens=321)

    req = seen[0]
    body = json.loads(req.content)
    assert (req.url.host, req.url.path) == (host, path)
    assert req.headers["authorization"] == "Bearer k"
    assert body["model"] == model and body[limit_param] == 321
    assert {k: body[k] for k in extra} == extra
    assert out.provider == provider and out.model == model
    assert (out.prompt_tokens, out.completion_tokens, out.cost_usd) == (120, 30, 0.0)
    assert chain.status()["provider"] == provider and chain.status()["fell_back"] is False


def test_a_rate_limited_free_tier_falls_through_to_the_next_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, limited = _mocked("groq", status=429)
    _, _, ok = _mocked("gemini")
    real = providers_module.OpenAI

    def by_host(**kw: Any) -> Any:
        handler = limited if "groq" in str(kw["base_url"]) else ok
        transport = httpx.MockTransport(handler)
        return real(**kw | {"max_retries": 0}, http_client=httpx.Client(transport=transport))

    monkeypatch.setattr(providers_module, "OpenAI", by_host)
    settings = Settings(
        _env_file=None,
        llm_providers=["groq", "gemini"],
        groq_api_key=SecretStr("k"),
        gemini_api_key=SecretStr("k"),
        ollama_base_url="",
    )
    chain = LLMChain.from_settings(settings)
    out = chain.complete("s", "u")
    assert out.provider == "gemini" and out.fallbacks == ["groq:RateLimitError"]
    status = chain.status()
    assert status["provider"] == "gemini"  # groq is benched for the cooldown
    assert status["fell_back"] is True and status["last_provider"] == "gemini"


def test_an_empty_reply_counts_as_a_failure() -> None:
    def create(**kw: Any) -> Any:
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=""))], usage=None
        )

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    chain = LLMChain([OpenAICompatibleProvider("groq", "m", client), Scripted("ollama")])
    assert chain.complete("s", "u").fallbacks == ["groq:EmptyReply"]


def test_status_without_any_provider_is_extractive() -> None:
    chain = LLMChain([])
    assert chain.status()["provider"] == "extractive"
    assert chain.status()["chain"] == ["extractive"]
    with pytest.raises(LLMUnavailable):
        chain.complete("s", "u")
    assert chain.last is None


def test_missing_keys_are_logged_by_name(caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(
        llm_providers=["groq", "gemini"],
        groq_api_key=None,
        gemini_api_key=SecretStr("k"),
        _env_file=None,
    )
    with caplog.at_level("INFO", logger="app.llm.providers"):
        providers = build_providers(settings)
    assert [p.name for p in providers] == ["gemini"]
    record = next(r for r in caplog.records if r.getMessage() == "model providers")
    assert record.skipped == {"groq": "no GROQ_API_KEY"}  # type: ignore[attr-defined]


def test_no_provider_at_all_is_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(llm_providers=["groq"], groq_api_key=None, _env_file=None)
    with caplog.at_level("WARNING", logger="app.llm.providers"):
        assert build_providers(settings) == []
    assert any("no model provider configured" in r.getMessage() for r in caplog.records)
