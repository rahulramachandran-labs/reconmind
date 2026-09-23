"""Specialist agents: run the domain's deterministic checks, then write up each
finding.

The checks establish the facts (what broke, how many records). A model, or the
adapter's template when no model is available, explains the likely cause and
the fix, grounded in retrieved runbooks and past incidents. Both write-ups are
kept, so a reader can compare what the model added.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.agents.deps import AgentDeps, traced_search
from app.agents.schemas import ModelWriteUp, SourceRef, WriteUp, fingerprint
from app.domain.protocol import DomainAdapter, Finding, FindingAnalysis, Scope
from app.llm.providers import Completion
from app.llm.structured import structured
from app.rag.prompts import UNTRUSTED_CONTEXT, format_passages
from app.retrieval.types import RetrievedChunk

PROMPT_VERSION = "specialist-analysis@4"

# times, ids like OUT-1071 or INC-0438, and numbers of two or more digits
_CLAIM = re.compile(r"\b(?:\d{1,2}:\d{2}|[A-Z]+-?\d{2,}|\d[\d,.]*\d)\b")


def ungrounded(analysis: FindingAnalysis, shown: str) -> str | None:
    """The times, ids and numbers in a write-up that appear nowhere in what the model
    was shown. A model may explain, but it may not bring in facts of its own."""
    seen = shown.replace(",", "")
    text = " ".join(
        [analysis.root_cause_hypothesis, *analysis.recommended_fix, *analysis.open_questions]
    )
    missing = []
    for claim in dict.fromkeys(_CLAIM.findall(text)):
        c = claim.replace(",", "").rstrip(".")
        if c in seen or (":" in c and c.replace(":", "").zfill(4) in seen):
            continue
        missing.append(claim)
    if not missing:
        return None
    return (
        f"these don't appear in the finding or the passages: {', '.join(missing[:6])}. "
        "Use only numbers, times and ids that are there, or leave them out."
    )


@dataclass
class Analysis:
    """One finding's write-up: what the report shows, the template it was held
    against, the passages behind it, and every model call it took."""

    shown: FindingAnalysis
    by: str  # the provider whose reply validated, or "template"
    template: FindingAnalysis
    sources: list[RetrievedChunk]
    calls: list[Completion] = field(default_factory=list)
    # why the model's reply was not used, when it was asked and rejected
    error: str | None = None


async def analyse(deps: AgentDeps, finding: Finding) -> Analysis:
    sources = traced_search(deps.retrieval, deps.adapter.retrieval_query(finding), deps.retrieval_k)
    template = deps.adapter.fallback_analysis(finding, sources)
    facts = finding.model_dump(mode="json", exclude={"evidence"}) | {
        "evidence": [e.summary for e in finding.evidence]
    }
    calls: list[Completion] = []
    notes: list[str] = []
    user = f"Finding:\n{json.dumps(facts, indent=1)}\n\n{format_passages(sources)}"
    shown_to_model = user + " ".join(e.summary for e in finding.evidence)
    shown, by = await structured(
        deps.llm,
        system=(
            "You are a senior data engineer writing up an incident. The facts were measured by "
            "deterministic checks and are correct; do not change numbers or severity. Explain the "
            "likely root cause, the fix (as steps), your confidence in the root cause (0-1), and "
            "open questions. Cite runbooks and past incidents where they apply, but don't treat "
            "a past incident's cause as this one's. Use only numbers, times and ids that appear "
            "in the finding or the passages.\n" + UNTRUSTED_CONTEXT
        ),
        user=user,
        schema=FindingAnalysis,
        fallback=lambda: template,
        name=f"analyse:{finding.finding_type}",
        prompt_version=PROMPT_VERSION,
        max_tokens=deps.report_max_tokens,
        calls=calls,
        check=lambda a: ungrounded(a, shown_to_model),
        notes=notes,
    )
    if by != "template":
        # a model may lower confidence freely but not talk itself far past the calibrated prior
        shown = shown.model_copy(
            update={"confidence": round(min(shown.confidence, template.confidence + 0.15, 0.95), 2)}
        )
    return Analysis(shown, by, template, sources, calls, notes[-1] if notes else None)


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


def written_item(deps: AgentDeps, f: Finding, a: Analysis) -> dict[str, Any]:
    template, model = write_ups(deps.adapter, f, a)
    return {
        "finding": f.model_dump(mode="json"),
        "analysis": a.shown.model_dump(mode="json"),
        "prior_confidence": a.template.confidence,
        "template": template.model_dump(mode="json"),
        "model_analysis": model.model_dump(mode="json") if model else None,
        "model_error": a.error if model is None else None,
        "sources": [SourceRef(**s.model_dump()).model_dump() for s in a.sources],
    }


def known_item(f: Finding, report: dict[str, Any]) -> dict[str, Any]:
    """A repeat of a finding already written up: carry the stored write-up along."""
    template = report.get("template") or {}
    return {
        "finding": f.model_dump(mode="json"),
        "analysis": {
            k: report[k]
            for k in ("root_cause_hypothesis", "recommended_fix", "confidence", "open_questions")
        },
        "prior_confidence": template.get("confidence", report["confidence"]),
        "template": template or None,
        "model_analysis": report.get("model_analysis"),
        "sources": report.get("sources", []),
    }


def build(role: str) -> Any:
    """One specialist node per role in the adapter's roster; the checks are the adapter's."""

    async def run(deps: AgentDeps, state: dict[str, Any]) -> dict[str, Any]:
        scope = Scope(**state["plan"]["scope"])
        findings = await deps.adapter.run_checks(role, deps.tools, scope)
        known = await asyncio.gather(
            *(
                asyncio.to_thread(deps.store.known_report, fingerprint(f.finding_type, f.title))
                for f in findings
            )
        )
        # a finding already written up doesn't need the model again; one that only has the
        # template's write-up gets the model's if a model is available now
        todo = [
            f
            for f, k in zip(findings, known, strict=True)
            if k is None or (deps.llm.enabled and not k.get("model_analysis"))
        ]
        written = await asyncio.gather(*(analyse(deps, f) for f in todo))
        by_finding = {id(f): a for f, a in zip(todo, written, strict=True)}
        items = []
        for f, k in zip(findings, known, strict=True):
            a = by_finding.get(id(f))
            items.append(written_item(deps, f, a) if a else known_item(f, k or {}))
        return {"findings": items}

    run.__name__ = role
    return run
