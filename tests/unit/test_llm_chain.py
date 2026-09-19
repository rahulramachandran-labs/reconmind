import time
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from app.core.config import Settings
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

    def complete(self, system: str, messages: list[Message], max_tokens: int) -> Completion:
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
