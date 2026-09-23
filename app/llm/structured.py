"""Pydantic-validated model output with a bounded re-prompt loop.

Models answer JSON in three shapes that are all technically prose: fenced in
markdown, prefaced with a sentence or a chain of thought, or both. Everything
before the first brace is stripped and the first balanced object is taken, so
only a reply that is truly not an object reaches the validator. What went wrong
is written onto the trace step of the attempt that produced it, so a failure can
be read in the Traces screen instead of guessed at.
"""

import json
import re
from collections.abc import Callable

from pydantic import BaseModel, ValidationError

from app.llm.providers import Completion, LLMUnavailable, Message
from app.llm.traced import TracedLLM
from app.observability.tracer import Step

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def _balanced(text: str, start: int) -> str:
    """The object beginning at ``start``, ignoring braces inside strings."""
    depth, in_string, escaped = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise ValueError("the JSON object is not closed; the reply was cut off")


def extract_json(text: str) -> dict[str, object]:
    """The first JSON object in a reply, whatever the model wrapped it in."""
    candidates = [m.group(1) for m in _FENCE.finditer(text)] + [text]
    for candidate in candidates:
        start = candidate.find("{")
        if start == -1:
            continue
        raw = _balanced(candidate, start)
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            raise ValueError("reply is not a JSON object")
        return obj
    raise ValueError("no JSON object in the reply")


async def structured[T: BaseModel](
    llm: TracedLLM,
    *,
    system: str,
    user: str,
    schema: type[T],
    fallback: Callable[[], T],
    name: str,
    prompt_version: str,
    retries: int = 2,
    max_tokens: int = 700,
    calls: list[Completion] | None = None,
    check: Callable[[T], str | None] | None = None,
    notes: list[str] | None = None,
) -> tuple[T, str]:
    """Ask for JSON matching ``schema``; re-prompt with the validation error up to
    ``retries`` times, then use ``fallback``. Returns the object and who produced it.
    ``check`` can reject a reply that parses but is wrong in a way the schema can't
    express; its message goes back to the model like a validation error. Every model
    reply is appended to ``calls`` when given, for latency and cost, and every reason
    a reply was rejected to ``notes``."""
    if not llm.enabled:
        return fallback(), "template"
    shape = json.dumps(schema.model_json_schema())
    messages = [
        Message(
            "user",
            f"{user}\n\nReply with one JSON object matching this JSON schema and nothing "
            f"else:\n{shape}",
        )
    ]
    for attempt in range(retries + 1):
        steps: list[Step] = []
        try:
            out = await llm.complete(
                system,
                messages,
                name=f"{name}#{attempt}" if attempt else name,
                prompt_version=prompt_version,
                max_tokens=max_tokens,
                json_object=True,
                steps=steps,
            )
        except LLMUnavailable as exc:
            if notes is not None:
                notes.append(f"no provider answered: {exc}")
            return fallback(), "template"
        if calls is not None:
            calls.append(out)
        try:
            obj = schema.model_validate(extract_json(out.text))
            problem = check(obj) if check else None
            if problem is None:
                return obj, out.provider
            problem = f"the reply parsed but was rejected: {problem}"
        except (ValueError, ValidationError) as exc:
            problem = _explain(exc, out)
        if notes is not None:
            notes.append(problem)
        for step in steps:  # the step is still pending, so this reaches the Traces screen
            step.output["validation_error"] = problem
            step.output["attempt"] = attempt
        messages += [
            Message("assistant", out.text),
            Message(
                "user",
                f"That did not validate: {problem}\n"
                "Reply again with only the corrected JSON object.",
            ),
        ]
    return fallback(), "template"


def _explain(exc: Exception, out: Completion) -> str:
    """The validation error, with the fields it names and why the reply was short."""
    if isinstance(exc, ValidationError):
        fields = ", ".join(".".join(str(p) for p in e["loc"]) or "(root)" for e in exc.errors())
        detail = f"{exc.error_count()} field(s) wrong ({fields}): {exc.errors()[0]['msg']}"
    else:
        detail = str(exc)
    if out.finish_reason == "length":
        detail += f"; the model stopped at the token limit after {out.completion_tokens} tokens"
    return detail[:600]
