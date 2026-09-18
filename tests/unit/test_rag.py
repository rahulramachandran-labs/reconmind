from app.llm import Completion, LLMChain, Message
from app.rag import answer_question, format_context, retrieval_query
from app.retrieval.types import RetrievedChunk


class StubRetrieval:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def search(self, query: str, k: int = 5) -> list[RetrievedChunk]:
        self.queries.append(query)
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


class Echo:
    name, model = "ollama", "tiny"

    def __init__(self) -> None:
        self.seen: list[Message] = []

    def complete(self, system: str, messages: list[Message], max_tokens: int) -> Completion:
        self.seen = messages
        return Completion(
            text="Latest file wins [1].",
            provider=self.name,
            model=self.model,
            latency_ms=3,
            prompt_tokens=50,
            completion_tokens=8,
        )


class Down:
    name, model = "openai", "x"

    def complete(self, system: str, messages: list[Message], max_tokens: int) -> Completion:
        raise TimeoutError


def test_answer_uses_chain_and_passes_history() -> None:
    echo = Echo()
    history = [Message("user", "earlier q"), Message("assistant", "earlier a")]
    ans = answer_question(
        "which file wins when a submitter resends a file?",
        StubRetrieval(),  # type: ignore[arg-type]
        LLMChain([echo]),
        history=history,
    )
    assert ans.provider == "ollama" and ans.prompt_tokens == 50
    assert [m.role for m in echo.seen] == ["user", "assistant", "user"]
    assert '<passage id="1" source="runbooks/dup.md"' in echo.seen[-1].content


def test_extractive_when_every_provider_fails() -> None:
    ans = answer_question("which submitter file wins?", StubRetrieval(), LLMChain([Down()]))  # type: ignore[arg-type]
    assert ans.provider == "extractive" and ans.fallbacks == ["openai:TimeoutError"]
    assert "[1]" in ans.answer


def test_extractive_when_no_provider_configured() -> None:
    ans = answer_question("which submitter file wins?", StubRetrieval(), LLMChain([]))  # type: ignore[arg-type]
    assert ans.provider == "extractive" and ans.fallbacks == []


def test_follow_ups_carry_the_previous_question_into_retrieval() -> None:
    history = [Message("user", "how do I detect key drift?"), Message("assistant", "...")]
    assert (
        retrieval_query("why does that happen?", history)
        == "how do I detect key drift? why does that happen?"
    )
    long_q = "what is the severity rubric for a volume drop between twenty five and fifty percent"
    assert retrieval_query(long_q, history) == long_q
    assert retrieval_query("why?", []) == "why?"


def test_context_is_wrapped_and_numbered() -> None:
    ctx = format_context(StubRetrieval().search("x") * 2)
    assert ctx.startswith("<context>") and ctx.endswith("</context>")
    assert ctx.count("<passage") == 2 and 'id="2"' in ctx
