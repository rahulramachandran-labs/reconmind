"""Specialist agents: run the domain's deterministic checks, then write up each
finding.

The checks establish the facts (what broke, how many records). A model, or the
adapter's template when no model is available, explains the likely cause and
the fix, grounded in retrieved runbooks and past incidents. Both write-ups are
kept, so a reader can compare what the model added.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.agents.deps import AgentDeps, traced_search
from app.agents.schemas import ModelWriteUp, SourceRef, WriteUp
from app.domain.protocol import DomainAdapter, Finding, FindingAnalysis, Scope
from app.llm.providers import Completion
from app.llm.structured import structured
from app.rag.prompts import UNTRUSTED_CONTEXT, format_passages
from app.retrieval.types import RetrievedChunk

PROMPT_VERSION = "specialist-analysis@3"


@dataclass
class Analysis:
    """One finding's write-up: what the report shows, the template it was held
    against, the passages behind it, and every model call it took."""

    shown: FindingAnalysis
    by: str  # the provider whose reply validated, or "template"
    template: FindingAnalysis
    sources: list[RetrievedChunk]
    calls: list[Completion] = field(default_factory=list)


async def analyse(deps: AgentDeps, finding: Finding) -> Analysis:
    sources = traced_search(deps.retrieval, deps.adapter.retrieval_query(finding), deps.retrieval_k)
    template = deps.adapter.fallback_analysis(finding, sources)
    facts = finding.model_dump(mode="json", exclude={"evidence"}) | {
        "evidence": [e.summary for e in finding.evidence]
    }
    calls: list[Completion] = []
    shown, by = await structured(
        deps.llm,
        system=(
            "You are a senior data engineer writing up an incident. The facts were measured by "
            "deterministic checks and are correct; do not change numbers or severity. Explain the "
            "likely root cause, the fix (as steps), your confidence in the root cause (0-1), and "
            "open questions. Cite runbooks and past incidents where they apply.\n"
            + UNTRUSTED_CONTEXT
        ),
        user=f"Finding:\n{json.dumps(facts, indent=1)}\n\n{format_passages(sources)}",
        schema=FindingAnalysis,
        fallback=lambda: template,
        name=f"analyse:{finding.finding_type}",
        prompt_version=PROMPT_VERSION,
        calls=calls,
    )
    if by != "template":
        # a model may lower confidence freely but not talk itself far past the calibrated prior
        shown = shown.model_copy(
            update={"confidence": round(min(shown.confidence, template.confidence + 0.15, 0.95), 2)}
        )
    return Analysis(shown, by, template, sources, calls)


def write_ups(
    adapter: DomainAdapter, finding: Finding, a: Analysis
) -> tuple[WriteUp, ModelWriteUp | None]:
    """The template's write-up, and the model's if a model's reply validated."""
    problem = adapter.problem_statement(finding)
    template = WriteUp(problem_statement=problem, **a.template.model_dump())
    if a.by == "template" or not a.calls:
        return template, None
    last = a.calls[-1]
    model = ModelWriteUp(
        problem_statement=problem,
        **a.shown.model_dump(),
        provider=last.provider,
        model=last.model,
        latency_ms=sum(c.latency_ms for c in a.calls),
        prompt_tokens=sum(c.prompt_tokens for c in a.calls),
        completion_tokens=sum(c.completion_tokens for c in a.calls),
        cost_usd=round(sum(c.cost_usd for c in a.calls), 6),
        prompt_version=PROMPT_VERSION,
        generated_at=datetime.now(UTC),
    )
    return template, model


def build(role: str) -> Any:
    """One specialist node per role in the adapter's roster; the checks are the adapter's."""

    async def run(deps: AgentDeps, state: dict[str, Any]) -> dict[str, Any]:
        scope = Scope(**state["plan"]["scope"])
        findings = await deps.adapter.run_checks(role, deps.tools, scope)
        analysed = await asyncio.gather(*(analyse(deps, f) for f in findings))
        items = []
        for f, a in zip(findings, analysed, strict=True):
            template, model = write_ups(deps.adapter, f, a)
            items.append(
                {
                    "finding": f.model_dump(mode="json"),
                    "analysis": a.shown.model_dump(mode="json"),
                    "prior_confidence": a.template.confidence,
                    "template": template.model_dump(mode="json"),
                    "model_analysis": model.model_dump(mode="json") if model else None,
                    "sources": [SourceRef(**s.model_dump()).model_dump() for s in a.sources],
                }
            )
        return {"findings": items}

    run.__name__ = role
    return run
