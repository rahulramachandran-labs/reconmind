"""Specialist agents: run the domain's deterministic checks, then write up each
finding.

The checks establish the facts (what broke, how many records). A model, or the
adapter's template when no model is available, explains the likely cause and
the fix, grounded in retrieved runbooks and past incidents.
"""

import asyncio
import json
from typing import Any

from app.agents.deps import AgentDeps, traced_search
from app.agents.schemas import SourceRef
from app.domain.protocol import Finding, FindingAnalysis, Scope
from app.llm.structured import structured
from app.rag.prompts import UNTRUSTED_CONTEXT, format_passages
from app.retrieval.types import RetrievedChunk

PROMPT_VERSION = "specialist-analysis@3"


async def analyse(
    deps: AgentDeps, finding: Finding
) -> tuple[FindingAnalysis, str, list[RetrievedChunk], float]:
    sources = traced_search(deps.retrieval, deps.adapter.retrieval_query(finding), deps.retrieval_k)
    prior = deps.adapter.fallback_analysis(finding, sources)
    facts = finding.model_dump(mode="json", exclude={"evidence"}) | {
        "evidence": [e.summary for e in finding.evidence]
    }
    analysis, by = await structured(
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
        fallback=lambda: prior,
        name=f"analyse:{finding.finding_type}",
        prompt_version=PROMPT_VERSION,
    )
    # a model may lower confidence freely but not talk itself far past the calibrated prior
    analysis.confidence = round(min(analysis.confidence, prior.confidence + 0.15, 0.95), 2)
    return analysis, by, sources, prior.confidence


def build(role: str) -> Any:
    """One specialist node per role in the adapter's roster; the checks are the adapter's."""

    async def run(deps: AgentDeps, state: dict[str, Any]) -> dict[str, Any]:
        scope = Scope(**state["plan"]["scope"])
        findings = await deps.adapter.run_checks(role, deps.tools, scope)
        analysed = await asyncio.gather(*(analyse(deps, f) for f in findings))
        return {
            "findings": [
                {
                    "finding": f.model_dump(mode="json"),
                    "analysis": a.model_dump(mode="json"),
                    "analysis_by": by,
                    "prior_confidence": prior,
                    "sources": [SourceRef(**s.model_dump()).model_dump() for s in src],
                }
                for f, (a, by, src, prior) in zip(findings, analysed, strict=True)
            ]
        }

    run.__name__ = role
    return run
