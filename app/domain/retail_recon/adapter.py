"""The retail adapter: what the agent layer sees of this domain.

The roster says which specialists exist and which questions they answer; the
checks, rubric and wording are in ``checks`` and ``writeups``.
"""

import asyncio
import re
from datetime import date, timedelta
from statistics import mean
from typing import Any

from app.domain.protocol import Finding, FindingAnalysis, Scope, Severity, SpecialistSpec, ToolBox
from app.domain.retail_recon import checks, writeups
from app.domain.retail_recon.rules import (
    DAG_ID,
    ORCHESTRATION,
    VOLUME_WINDOW_DAYS,
    WAREHOUSE,
    latest_file_per_submitter,
)
from app.retrieval.types import RetrievedChunk

_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


class RetailReconAdapter:
    name = "retail_recon"
    title = "Retail transaction reconciliation"
    scan_keywords = [
        "scan",
        "check the pipeline",
        "anything wrong",
        "any issues",
        "what's wrong",
        "what is wrong",
        "health",
        "problems",
        "incidents",
        "everything ok",
        "investigate",
    ]
    specialists = [
        SpecialistSpec(
            role="reconciliation",
            title="Reconciliation",
            description=(
                "Applies the dedup key and the latest-file-wins rule, and flags outlet / "
                "location key drift."
            ),
            finding_types=["duplicate_submission", "key_drift"],
            keywords=[
                "duplicate",
                "dedup",
                "resend",
                "resent",
                "twice",
                "double",
                "superseded",
                "drift",
                "outlet",
                "location",
                "two ids",
                "store",
                "reconcil",
                "key",
            ],
        ),
        SpecialistSpec(
            role="data_quality",
            title="Data-Quality",
            description=(
                "Diffs each batch against the dbt contract and checks volume and timing "
                "against DAG history."
            ),
            finding_types=["schema_drift", "volume_anomaly"],
            keywords=[
                "schema",
                "column",
                "renamed",
                "dropped",
                "contract",
                "header",
                "volume",
                "light",
                "rows",
                "count",
                "late",
                "sla",
                "dag",
                "task",
                "failed",
                "sensor",
                "missing",
                "truncated",
                "anomal",
            ],
        ),
    ]

    # -- scope ---------------------------------------------------------------

    async def resolve_scope(self, question: str | None, tools: ToolBox) -> Scope:
        runs = await tools.call(ORCHESTRATION, "list_dag_runs", {"dag_id": DAG_ID})
        dates = sorted(r["business_date"] for r in runs["runs"])
        last = date.fromisoformat(dates[-1]) if dates else date.today()
        first = date.fromisoformat(dates[0]) if dates else last - timedelta(days=20)
        mentioned = sorted(_DATE.findall(question or ""))
        if mentioned:
            d0 = date.fromisoformat(mentioned[0])
            d1 = date.fromisoformat(mentioned[-1])
            # keep a week of history before the day asked about, for trailing averages
            return Scope(date_from=max(first, d0 - timedelta(days=VOLUME_WINDOW_DAYS)), date_to=d1)
        return Scope(date_from=first, date_to=last)

    # -- checks ------------------------------------------------------------------

    async def run_checks(self, role: str, tools: ToolBox, scope: Scope) -> list[Finding]:
        if role == "reconciliation":
            dups, drift = await asyncio.gather(
                checks.duplicate_submissions(tools, scope), checks.key_drift(tools, scope)
            )
            findings = dups + drift
        elif role == "data_quality":
            findings = await checks.data_quality(tools, scope)
        else:
            raise ValueError(f"unknown specialist {role}")
        for f in findings:
            f.severity = self.severity(f)
        return findings

    # -- rubric and wording --------------------------------------------------------

    def severity(self, finding: Finding) -> Severity:
        return writeups.severity(finding)

    def problem_statement(self, finding: Finding) -> str:
        return writeups.problem_statement(finding)

    def retrieval_query(self, finding: Finding) -> str:
        return writeups.retrieval_query(finding)

    def fallback_analysis(self, finding: Finding, sources: list[RetrievedChunk]) -> FindingAnalysis:
        return writeups.fallback_analysis(finding, sources)

    # -- dashboard ---------------------------------------------------------------

    async def overview(self, tools: ToolBox) -> dict[str, Any]:
        """Volume for the latest business date against its trailing week, and the last run."""
        runs = (await tools.call(ORCHESTRATION, "list_dag_runs", {"dag_id": DAG_ID}))["runs"]
        if not runs:
            return {"as_of": None, "volume": None, "last_run": None}
        runs.sort(key=lambda r: r["business_date"])
        last = runs[-1]
        as_of = date.fromisoformat(last["business_date"])
        days = [as_of - timedelta(days=i) for i in range(13, -1, -1)]
        stats = await asyncio.gather(
            *(
                tools.call(WAREHOUSE, "get_table_stats", {"table": "transactions", "date": str(d)})
                for d in days
            )
        )
        series = []
        for d, day in zip(days, stats, strict=True):
            latest = latest_file_per_submitter(day["files"])
            series.append(
                {
                    "date": str(d),
                    "rows": sum(f["rows"] for f in latest.values()),
                    "by_submitter": {k: v["rows"] for k, v in sorted(latest.items())},
                }
            )
        trailing = [s["rows"] for s in series[-1 - VOLUME_WINDOW_DAYS : -1] if s["rows"]]
        avg = mean(trailing) if trailing else 0.0
        today = series[-1]["rows"]
        return {
            "as_of": str(as_of),
            "volume": {
                "rows": today,
                "trailing_avg_7d": round(avg, 1),
                "pct_change": round(today / avg - 1, 3) if avg else None,
                "series": series,
            },
            "last_run": {
                "business_date": last["business_date"],
                "state": last["state"],
                "duration_s": last["duration_s"],
                "failed_tasks": last["failed_tasks"],
                "runs_failed_14d": sum(1 for r in runs[-14:] if r["state"] == "failed"),
            },
        }
