"""Planner agent: decides whether a question needs the runbooks or a live
investigation, and which specialists should look.

Keyword rules make the first call. When a model is available it may refine the
routing, but only to specialists the domain adapter defines.
"""

import re
import uuid
from typing import Any

from app.agents.deps import AgentDeps
from app.agents.schemas import PlannerDecision
from app.domain.protocol import DomainAdapter
from app.llm.structured import structured

PROMPT_VERSION = "planner@2"

_KNOWLEDGE = re.compile(
    r"^(what|what's|how|which|why does|why do|can i|can we|should|when|who|is a|is an|does|do i|"
    r"explain|define|tell me about)\b",
    re.I,
)
_INVESTIGATE = re.compile(
    r"\b(are there|any |did we|did the|in the data|right now|today|latest|this week|last week|"
    r"check|scan|find|show me|look at|investigate|what happened|what went wrong|going on|"
    r"20\d\d-\d\d-\d\d)",
    re.I,
)


def heuristic_plan(adapter: DomainAdapter, trigger: str, question: str | None) -> PlannerDecision:
    roles = [s.role for s in adapter.specialists]
    if trigger == "scan" or not question:
        return PlannerDecision(
            intent="investigate", specialists=roles, confidence=1.0, rationale="Scheduled scan."
        )
    q = question.lower()
    if any(k in q for k in adapter.scan_keywords):
        return PlannerDecision(
            intent="investigate",
            specialists=roles,
            confidence=0.85,
            rationale="Asked for a general check, so every specialist looks.",
        )
    matched_specs = [s for s in adapter.specialists if any(k in q for k in s.keywords)]
    matched = [s.role for s in matched_specs]
    investigative = bool(_INVESTIGATE.search(q))
    knowledge = bool(_KNOWLEDGE.match(q.strip()))
    if knowledge and not investigative:
        return PlannerDecision(
            intent="answer",
            specialists=[],
            confidence=0.8,
            rationale="A how/what question the runbooks can answer without touching the data.",
        )
    if matched:
        return PlannerDecision(
            intent="investigate",
            specialists=matched,
            confidence=0.85 if investigative else 0.6,
            rationale="Sounds like a job for "
            + " and ".join(s.title for s in matched_specs)
            + ", so only that looks.",
        )
    if investigative:
        return PlannerDecision(
            intent="investigate",
            specialists=roles,
            confidence=0.65,
            rationale="Asks about the data but not about a specific failure, so check everything.",
        )
    return PlannerDecision(
        intent="unclear",
        specialists=[],
        confidence=0.3,
        rationale="Could not tell what part of the pipeline this is about.",
    )


async def run(deps: AgentDeps, state: dict[str, Any]) -> dict[str, Any]:
    adapter = deps.adapter
    trigger, question = state["trigger"], state.get("question")
    prior = heuristic_plan(adapter, trigger, question)
    decision, by = prior, "rules"
    if trigger != "scan" and question and deps.llm.enabled:
        roster = "\n".join(
            f"- {s.role}: {s.description} (finds: {', '.join(s.finding_types)})"
            for s in adapter.specialists
        )
        decision, by = await structured(
            deps.llm,
            system=(
                "You route questions about a data pipeline to specialist agents.\n"
                "intent=answer when the runbooks alone can answer it (how/what/why in general);\n"
                "intent=investigate when it needs a look at the actual data or runs;\n"
                "intent=unclear when you cannot tell. Only use the specialists listed."
            ),
            user=(
                f"Specialists:\n{roster}\n\nQuestion: {question}\n\n"
                f"A keyword router suggested: {prior.model_dump_json()}"
            ),
            schema=PlannerDecision,
            fallback=lambda: prior,
            name="planner",
            prompt_version=PROMPT_VERSION,
        )
        allowed = {s.role for s in adapter.specialists}
        decision.specialists = [s for s in decision.specialists if s in allowed]
        if decision.intent == "investigate" and not decision.specialists:
            decision.specialists = sorted(allowed)
    scope = await adapter.resolve_scope(question, deps.tools)
    out = decision.model_dump() | {
        "planned_by": by,
        "scope": scope.model_dump(mode="json"),
        "needs_review": decision.confidence < deps.planner_threshold,
    }
    deps.store.save_plan(uuid.UUID(state["run_id"]), out)
    return {"plan": out}
