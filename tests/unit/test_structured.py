import pytest
from pydantic import BaseModel, Field

from app.llm.providers import LLMChain, Message
from app.llm.structured import extract_json, structured
from app.llm.traced import TracedLLM, UntracedCall
from app.observability.tracer import RunTracer
from tests.fakes import ScriptedProvider


class Pick(BaseModel):
    colour: str = Field(pattern="^(red|blue)$")
    score: float = Field(ge=0, le=1)


def test_extract_json_from_fences_and_prose() -> None:
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": 2} hope that helps') == {"a": 2}
    with pytest.raises(ValueError):
        extract_json("no json here")


async def _run(
    replies: list[str], retries: int = 2
) -> tuple[Pick, str, ScriptedProvider, RunTracer]:
    it = iter(replies)
    provider = ScriptedProvider(lambda s, m: next(it))
    tracer = RunTracer(__import__("uuid").uuid4())
    async with tracer.activate():
        out, by = await structured(
            TracedLLM(LLMChain([provider])),
            system="s",
            user="pick a colour",
            schema=Pick,
            fallback=lambda: Pick(colour="blue", score=0.1),
            name="pick",
            prompt_version="t@1",
            retries=retries,
        )
    return out, by, provider, tracer


async def test_valid_first_time() -> None:
    out, by, provider, tracer = await _run(['{"colour": "red", "score": 0.4}'])
    assert out.colour == "red" and by == "scripted" and len(provider.calls) == 1
    assert [s.kind for s in tracer.steps] == ["llm"]


async def test_reprompts_with_the_validation_error() -> None:
    out, _, provider, tracer = await _run(
        ['{"colour": "green", "score": 3}', '{"colour": "red", "score": 0.5}']
    )
    assert out.colour == "red"
    second = provider.calls[1][1]
    assert second[-1].role == "user" and "did not validate" in second[-1].content
    assert [s.name for s in tracer.steps] == ["pick", "pick#1"]


async def test_gives_up_after_two_retries_and_uses_the_fallback() -> None:
    out, by, provider, _ = await _run(["nope"] * 5)
    assert len(provider.calls) == 3
    assert by == "template" and out.colour == "blue"


async def test_no_model_means_template_without_calls() -> None:
    tracer = RunTracer(__import__("uuid").uuid4())
    async with tracer.activate():
        _, by = await structured(
            TracedLLM(LLMChain([])),
            system="s",
            user="u",
            schema=Pick,
            fallback=lambda: Pick(colour="red", score=1),
            name="n",
            prompt_version="v",
        )
    assert by == "template" and tracer.steps == []


async def test_llm_calls_outside_a_run_are_refused() -> None:
    llm = TracedLLM(LLMChain([ScriptedProvider(lambda s, m: "x")]))
    with pytest.raises(UntracedCall):
        await llm.complete("s", [Message("user", "u")], name="n", prompt_version="v")


async def test_a_check_can_reject_a_reply_that_parses() -> None:
    replies = iter(['{"colour": "red", "score": 0.9}', '{"colour": "red", "score": 0.4}'])
    provider = ScriptedProvider(lambda s, m: next(replies))
    tracer = RunTracer(__import__("uuid").uuid4())
    async with tracer.activate():
        out, by = await structured(
            TracedLLM(LLMChain([provider])),
            system="s",
            user="pick a colour",
            schema=Pick,
            fallback=lambda: Pick(colour="blue", score=0.1),
            name="pick",
            prompt_version="t@1",
            check=lambda p: "too sure of itself" if p.score > 0.5 else None,
        )
    assert out.score == 0.4 and by == "scripted"
    assert "too sure of itself" in provider.calls[1][1][-1].content
