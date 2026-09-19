"""Reporter agent: turns the specialists' findings into incident reports and a
run summary, and decides which reports need a human sign-off."""

import json
import uuid
from typing import Any

from app.agents.deps import AgentDeps
from app.agents.schemas import (
    AffectedRecords,
    IncidentReport,
    ModelWriteUp,
    RunSummary,
    SourceRef,
    WriteUp,
    confidence_label,
)
from app.domain.protocol import SEVERITY_ORDER, Finding, FindingAnalysis
from app.llm.structured import structured
from app.observability.tracer import current_tracer
from app.rag.prompts import UNTRUSTED_CONTEXT

PROMPT_VERSION = "reporter-summary@2"


def _summary_fallback(reports: list[IncidentReport]) -> RunSummary:
    if not reports:
        return RunSummary(
            headline="No incidents found", summary="Every check passed for the window."
        )
    worst = min(reports, key=lambda r: SEVERITY_ORDER[r.severity]).severity
    new = sum(1 for r in reports if not r.repeat)
    lines = [
        f"- {r.severity} {r.title}" + (" (already reported, still there)" if r.repeat else "")
        for r in reports
    ]
    headline = f"{len(reports)} finding{'s' if len(reports) != 1 else ''}, worst {worst}"
    if new < len(reports):
        headline += f"; {new} new"
    return RunSummary(headline=headline, summary="\n".join(lines))


async def run(deps: AgentDeps, state: dict[str, Any]) -> dict[str, Any]:
    run_id = uuid.UUID(state["run_id"])
    tracer = current_tracer()
    items = sorted(
        state.get("findings", []),
        key=lambda x: (SEVERITY_ORDER[x["finding"]["severity"]], -x["finding"]["affected_records"]),
    )
    reports = []
    for item in items:
        f = Finding(**item["finding"])
        a = FindingAnalysis(**item["analysis"])
        reasons = []
        if f.severity == "S1":
            reasons.append("S1 findings always get a human sign-off")
        # a model can push a finding into review but never talk it out of one
        gate = min(a.confidence, item.get("prior_confidence", a.confidence))
        if gate < deps.review_threshold:
            reasons.append(f"root-cause confidence {gate:.2f} is below {deps.review_threshold}")
        reports.append(
            IncidentReport(
                id=uuid.uuid4(),
                run_id=run_id,
                finding_type=f.finding_type,
                specialist=f.specialist,
                severity=f.severity,
                title=f.title,
                problem_statement=deps.adapter.problem_statement(f),
                affected_records=AffectedRecords(
                    count=f.affected_records,
                    rate=f.affected_rate,
                    detail=f"{f.affected_records} records"
                    + (f" ({abs(f.affected_rate):.1%})" if f.affected_rate is not None else ""),
                ),
                root_cause_hypothesis=a.root_cause_hypothesis,
                recommended_fix=a.recommended_fix,
                confidence=a.confidence,
                confidence_label=confidence_label(a.confidence),
                open_questions=a.open_questions,
                evidence=f.evidence,
                sources=[SourceRef(**s) for s in item["sources"]],
                analysis_by="model" if item.get("model_analysis") else "template",
                needs_review=bool(reasons),
                review_reason="; ".join(reasons) or None,
                trace_url=tracer.trace_url if tracer else None,
                status="pending_review" if reasons else "published",
                template=WriteUp(**item["template"]) if item.get("template") else None,
                model_analysis=(
                    ModelWriteUp(**item["model_analysis"]) if item.get("model_analysis") else None
                ),
            )
        )
    # repeats of findings an earlier scan reported come back resolved to that report
    reports = deps.store.save_reports(run_id, reports)
    fallback = _summary_fallback(reports)
    summary, _ = (
        await structured(
            deps.llm,
            system=(
                "Summarise an incident scan for the on-call data engineer in plain language: "
                "a one-line headline and a short summary that leads with the most severe finding. "
                f"Keep every number exactly as given.\n{UNTRUSTED_CONTEXT}"
            ),
            user=json.dumps(
                [
                    {
                        "severity": r.severity,
                        "title": r.title,
                        "problem": r.problem_statement,
                        "already_reported": r.repeat,
                    }
                    for r in reports
                ],
                indent=1,
            ),
            schema=RunSummary,
            fallback=lambda: fallback,
            name="reporter:summary",
            prompt_version=PROMPT_VERSION,
        )
        if reports
        else (fallback, "template")
    )
    return {
        "reports": [r.model_dump(mode="json") for r in reports],
        "summary": summary.model_dump(),
    }
