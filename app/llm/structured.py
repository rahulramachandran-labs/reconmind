"""Pydantic-validated model output with a bounded re-prompt loop."""

import json
import re
from collections.abc import Callable

from pydantic import BaseModel, ValidationError

from app.llm.providers import LLMUnavailable, Message
from app.llm.traced import TracedLLM

_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def extract_json(text: str) -> dict[str, object]:
    m = _FENCE.search(text)
    raw = m.group(1) if m else text[text.find("{") : text.rfind("}") + 1]
    if not raw:
        raise ValueError("no JSON object in the reply")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("reply is not a JSON object")
    return obj


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
) -> tuple[T, str]:
    """Ask for JSON matching ``schema``; re-prompt with the validation error up to
    ``retries`` times, then use ``fallback``. Returns the object and who produced it."""
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
        try:
            out = await llm.complete(
                system,
                messages,
                name=f"{name}#{attempt}" if attempt else name,
                prompt_version=prompt_version,
            )
        except LLMUnavailable:
            return fallback(), "template"
        try:
            return schema.model_validate(extract_json(out.text)), out.provider
        except (ValueError, ValidationError) as exc:
            messages += [
                Message("assistant", out.text),
                Message(
                    "user",
                    f"That did not validate: {str(exc)[:600]}\n"
                    "Reply again with only the corrected JSON object.",
                ),
            ]
    return fallback(), "template"
