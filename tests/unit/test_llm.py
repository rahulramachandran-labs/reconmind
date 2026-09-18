from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.llm import LLMClient, LLMUnavailable
from app.rag import answer_question, format_context
from app.retrieval.types import RetrievedChunk


class FakeCompletions:
    def __init__(self, text: str = "answer [1]", fail: bool = False) -> None:
        self.text, self.fail, self.calls = text, fail, []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.fail:
            raise TimeoutError("connection refused")
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=f"  {self.text} "))],
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=30),
        )


def fake_client(**kw: Any) -> Any:
    completions = FakeCompletions(**kw)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions)), completions


def test_ollama_provider_uses_configured_model() -> None:
    client, calls = fake_client()
    llm = LLMClient(Settings(llm_provider="ollama", ollama_model="tiny"), client=client)
    out = llm.complete("sys", "user")
    assert out.text == "answer [1]"
    assert out.provider == "ollama" and out.model == "tiny"
    assert out.prompt_tokens == 120 and out.completion_tokens == 30
    assert calls.calls[0]["messages"][0] == {"role": "system", "content": "sys"}


def test_openai_without_key_is_disabled() -> None:
    llm = LLMClient(Settings(llm_provider="openai", openai_api_key=None))
    assert not llm.enabled
    with pytest.raises(LLMUnavailable):
        llm.complete("s", "u")


def test_openai_with_key_is_enabled() -> None:
    llm = LLMClient(Settings(llm_provider="openai", openai_api_key=SecretStr("sk-test")))
    assert llm.enabled and llm.model == "gpt-5-mini"


def test_provider_errors_are_wrapped() -> None:
    client, _ = fake_client(fail=True)
    llm = LLMClient(Settings(llm_provider="ollama"), client=client)
    with pytest.raises(LLMUnavailable, match="connection refused"):
        llm.complete("s", "u")


class StubRetrieval:
    def search(self, query: str, k: int = 5) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id="c1",
                doc_id="d",
                title="Dup",
                path="runbooks/dup.md",
                section="Rule",
                doc_type="runbook",
                text="Dup | Rule\nThe latest submitter file wins.",
                score=0.9,
                rank=1,
            )
        ]


def test_answer_uses_llm_when_available() -> None:
    client, calls = fake_client(text="Latest file wins [1].")
    llm = LLMClient(Settings(llm_provider="ollama"), client=client)
    ans = answer_question("which file wins?", StubRetrieval(), llm)  # type: ignore[arg-type]
    assert ans.provider == "ollama" and ans.answer == "Latest file wins [1]."
    prompt = calls.calls[0]["messages"][1]["content"]
    assert '<passage id="1" source="runbooks/dup.md"' in prompt


def test_answer_falls_back_to_extractive_when_llm_fails() -> None:
    client, _ = fake_client(fail=True)
    llm = LLMClient(Settings(llm_provider="ollama"), client=client)
    ans = answer_question("which submitter file wins?", StubRetrieval(), llm)  # type: ignore[arg-type]
    assert ans.provider == "extractive"
    assert "[1]" in ans.answer


def test_format_context_numbers_passages() -> None:
    ctx = format_context(StubRetrieval().search("x") * 2)
    assert ctx.count("<passage") == 2 and 'id="2"' in ctx
