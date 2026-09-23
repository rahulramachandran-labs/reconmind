"""The structured loop against replies Groq actually sent.

The fixtures are raw responses captured from the account the hosted demo runs on:
a plain object, one from JSON mode, one wrapped in reasoning and a markdown fence,
and one cut off at the token limit.
"""

import json
import uuid
from pathlib import Path

import pytest

from app.domain.protocol import FindingAnalysis
from app.llm.providers import Completion, LLMChain
from app.llm.structured import _explain, extract_json, structured
from app.llm.traced import TracedLLM
from app.observability.tracer import RunTracer
from tests.fakes import ScriptedProvider

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "llm" / "groq"
COMPLETE = [
    "openai-gpt-oss-120b.txt",
    "openai-gpt-oss-120b-jsonmode.txt",
    "gpt-oss-120b-fenced-with-preamble.txt",
]


@pytest.mark.parametrize("name", COMPLETE)
def test_every_complete_reply_parses_to_an_analysis(name: str) -> None:
    text = (FIXTURES / name).read_text()
    analysis = FindingAnalysis.model_validate(extract_json(text))
    assert analysis.root_cause_hypothesis and analysis.recommended_fix
    assert 0.0 <= analysis.confidence <= 1.0


def test_a_reply_that_opens_with_reasoning_and_a_fence_still_parses() -> None:
    text = (FIXTURES / "gpt-oss-120b-fenced-with-preamble.txt").read_text()
    assert text.lstrip().startswith("**Thinking**") and "```" in text
    assert "root_cause_hypothesis" in extract_json(text)


def test_a_truncated_reply_is_reported_as_cut_off() -> None:
    text = (FIXTURES / "gpt-oss-120b-truncated.txt").read_text()
    with pytest.raises(ValueError, match="cut off"):
        extract_json(text)


def test_prose_after_the_object_does_not_break_parsing() -> None:
    body = json.dumps({"a": 1, "b": {"c": "}"}})
    assert extract_json(f"Here it is:\n{body}\nLet me know if you want more.") == {
        "a": 1,
        "b": {"c": "}"},
    }


def test_the_explanation_names_the_field_and_the_token_limit() -> None:
    try:
        FindingAnalysis.model_validate({"recommended_fix": []})
    except Exception as exc:
        out = Completion("", "groq", "m", 1, completion_tokens=120, finish_reason="length")
        message = _explain(exc, out)
    assert "root_cause_hypothesis" in message
    assert "token limit after 120 tokens" in message


async def test_a_cut_off_reply_is_retried_with_the_reason_quoted() -> None:
    replies = iter(
        [
            (FIXTURES / "gpt-oss-120b-truncated.txt").read_text(),
            (FIXTURES / "openai-gpt-oss-120b.txt").read_text(),
        ]
    )
    provider = ScriptedProvider(lambda s, m: next(replies))
    tracer = RunTracer(uuid.uuid4())
    notes: list[str] = []
    async with tracer.activate():
        analysis, by = await structured(
            TracedLLM(LLMChain([provider])),
            system="s",
            user="u",
            schema=FindingAnalysis,
            fallback=lambda: FindingAnalysis(
                root_cause_hypothesis="t",
                recommended_fix=["t"],
                confidence=0.5,
                open_questions=[],
            ),
            name="analyse",
            prompt_version="test@1",
            notes=notes,
        )
    assert by == "scripted" and analysis.root_cause_hypothesis
    assert notes and "cut off" in notes[0]
    # the retry quotes what was wrong, and the failure is on the step that caused it
    assert "did not validate" in provider.calls[1][1][-1].content
    assert "cut off" in provider.calls[1][1][-1].content
    assert tracer.steps[0].output["validation_error"].startswith("the JSON object is not closed")
    assert provider.json_asked is True
