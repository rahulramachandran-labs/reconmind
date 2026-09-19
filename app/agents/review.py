"""Human-in-the-loop checkpoints.

Each node calls LangGraph's ``interrupt()``: the run is checkpointed and stops
until a reviewer's decision arrives through the API, then resumes from the same
point, on any API instance, because the checkpoint lives in Postgres.
"""

import uuid
from typing import Any

from langgraph.types import interrupt

from app.agents.deps import AgentDeps


async def plan_review(deps: AgentDeps, state: dict[str, Any]) -> dict[str, Any]:
    """The Planner was unsure what to do; a person picks the specialists or rejects."""
    plan = state["plan"]
    decision = interrupt(
        {
            "kind": "plan",
            "question": state.get("question"),
            "proposed": {k: plan[k] for k in ("intent", "specialists", "confidence", "rationale")},
            "options": [s.role for s in deps.adapter.specialists],
        }
    )
    return {"plan_review": decision}


async def report_review(deps: AgentDeps, state: dict[str, Any]) -> dict[str, Any]:
    """S1 or low-confidence reports wait for approve / reject / annotate."""
    pending = [
        r
        for r in state.get("reports", [])
        if r["status"] == "pending_review" and not r.get("repeat")
    ]
    decisions = interrupt(
        {
            "kind": "reports",
            "reports": [
                {k: r[k] for k in ("id", "title", "severity", "review_reason")} for r in pending
            ],
        }
    )
    outcome = deps.store.apply_decisions(uuid.UUID(state["run_id"]), decisions)
    return {"review_outcome": outcome}
