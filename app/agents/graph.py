"""The investigation graph.

    planner --(low confidence)--> plan_review --+
       |                                        |
       +--(answer)--> answer -------------------+--> finalize
       |                                        |
       +--(investigate)--> one node per specialist (run concurrently)
                                  |
                               reporter --(S1 or low confidence)--> report_review --> finalize

The specialist nodes are created from the domain adapter, so the same graph
runs on any adapter. Each agent lives in its own module (planner, specialists,
reporter, answerer, review); this file only wires them together.
"""

import operator
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents import answerer, planner, reporter, review, specialists
from app.agents.deps import AgentDeps
from app.observability.tracer import RunTracer


class InvestigationState(TypedDict, total=False):
    run_id: str
    trigger: str
    question: str | None
    history: list[dict[str, str]]
    plan: dict[str, Any]
    plan_review: dict[str, Any]
    findings: Annotated[list[dict[str, Any]], operator.add]
    reports: list[dict[str, Any]]
    summary: dict[str, Any]
    review_outcome: list[dict[str, Any]]
    answer: str
    answer_provider: str
    sources: list[dict[str, Any]]


NodeFn = Callable[[AgentDeps, dict[str, Any]], Awaitable[dict[str, Any]]]
TracerFor = Callable[[str], RunTracer]


def build_graph(
    deps: AgentDeps, tracer_for: TracerFor, checkpointer: BaseCheckpointSaver[Any] | None
) -> CompiledStateGraph[Any, Any, Any, Any]:
    roles = [s.role for s in deps.adapter.specialists]

    def traced(name: str, fn: NodeFn) -> Any:
        async def node(state: InvestigationState) -> dict[str, Any]:
            tracer = tracer_for(state["run_id"])
            async with tracer.node(name, {"keys": sorted(state)}) as step:
                update = await fn(deps, dict(state))
                step.output = {"keys": sorted(update)}
                return update

        node.__name__ = name
        return node

    async def finalize(deps: AgentDeps, state: dict[str, Any]) -> dict[str, Any]:
        return {}

    g: StateGraph[InvestigationState] = StateGraph(InvestigationState)
    g.add_node("planner", traced("planner", planner.run))
    g.add_node("plan_review", traced("plan_review", review.plan_review))
    g.add_node("answer", traced("answer", answerer.run))
    for role in roles:
        g.add_node(role, traced(role, specialists.build(role)))
    g.add_node("reporter", traced("reporter", reporter.run))
    g.add_node("report_review", traced("report_review", review.report_review))
    g.add_node("finalize", traced("finalize", finalize))

    def dispatch(plan: dict[str, Any]) -> list[str]:
        if plan["intent"] == "investigate" and plan["specialists"]:
            return list(plan["specialists"])  # same superstep: they run concurrently
        return ["answer"]

    def after_plan(state: InvestigationState) -> list[str]:
        plan = state["plan"]
        if plan["needs_review"]:
            return ["plan_review"]
        return dispatch(plan)

    def after_plan_review(state: InvestigationState) -> list[str]:
        decision = state.get("plan_review") or {}
        if decision.get("decision") == "reject":
            return ["finalize"]
        plan = dict(state["plan"])
        chosen = [s for s in decision.get("specialists") or [] if s in roles]
        if chosen:
            plan |= {"intent": "investigate", "specialists": chosen}
        elif plan["intent"] == "unclear":
            plan |= {"intent": "answer"}
        return dispatch(plan)

    def after_report(state: InvestigationState) -> str:
        # a repeat that is still waiting for review is already in the queue under its first run
        pending = any(
            r["status"] == "pending_review" and not r.get("repeat")
            for r in state.get("reports", [])
        )
        return "report_review" if pending else "finalize"

    targets = ["plan_review", "answer", *roles]
    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", after_plan, targets)
    g.add_conditional_edges("plan_review", after_plan_review, ["finalize", "answer", *roles])
    for role in roles:
        g.add_edge(role, "reporter")
    g.add_conditional_edges("reporter", after_report, ["report_review", "finalize"])
    g.add_edge("report_review", "finalize")
    g.add_edge("answer", "finalize")
    g.add_edge("finalize", END)
    return g.compile(checkpointer=checkpointer)
