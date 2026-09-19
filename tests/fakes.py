"""Scripted stand-ins for model providers."""

import json
from collections.abc import Callable

from app.llm.providers import Completion, Message

Responder = Callable[[str, list[Message]], str]


class ScriptedProvider:
    """Answers with whatever ``respond`` returns and counts every call."""

    def __init__(self, respond: Responder, name: str = "scripted", model: str = "fake-1") -> None:
        self.name, self.model, self.respond = name, model, respond
        self.calls: list[tuple[str, list[Message]]] = []

    def complete(self, system: str, messages: list[Message], max_tokens: int) -> Completion:
        self.calls.append((system, messages))
        return Completion(
            text=self.respond(system, messages),
            provider=self.name,
            model=self.model,
            latency_ms=2,
            prompt_tokens=100,
            completion_tokens=20,
            cost_usd=0.0001,
        )


def well_behaved(system: str, messages: list[Message]) -> str:
    """Valid JSON for whichever schema the prompt asks for."""
    prompt = messages[-1].content if messages else ""
    first = messages[0].content if messages else ""
    if "route questions" in system:
        return json.dumps(
            {
                "intent": "investigate",
                "specialists": ["reconciliation", "not_a_role"],
                "confidence": 0.9,
                "rationale": "asks about duplicates in the data",
            }
        )
    if "Summarise an incident scan" in system:
        return json.dumps({"headline": "Scan found problems", "summary": "See the findings below."})
    if "writing up an incident" in system:
        return json.dumps(
            {
                "root_cause_hypothesis": "Model says: the submitter's export changed.",
                "recommended_fix": ["Ask for a resend."],
                "confidence": 0.9,
                "open_questions": ["When did it start?"],
            }
        )
    return f"Answer from the model about: {first[:40]} {prompt[:10]}"
