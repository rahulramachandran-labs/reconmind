"""A second, deliberately small domain: customer support ticket triage.

It exists to prove that nothing in the agent layer is retail specific. It has
its own specialists, finding types and rubric, and needs no MCP tools at all.
See README.md in this folder for how to turn it into a real adapter.
"""

from datetime import date, datetime
from typing import Any

from app.domain.protocol import (
    Evidence,
    Finding,
    FindingAnalysis,
    Scope,
    Severity,
    SpecialistSpec,
    ToolBox,
)
from app.retrieval.types import RetrievedChunk

# (ticket_id, customer_id, subject, opened_at, first_response_at)
TICKETS = [
    ("T-101", "C-7", "Cannot export invoices", "2026-06-02T09:00", "2026-06-02T09:40"),
    ("T-102", "C-7", "cannot export invoices!!", "2026-06-02T09:05", "2026-06-02T11:00"),
    ("T-103", "C-9", "Password reset loop", "2026-06-02T10:00", "2026-06-02T16:30"),
    ("T-104", "C-3", "Billing address change", "2026-06-03T08:00", "2026-06-03T08:20"),
]
FIRST_RESPONSE_SLA_MIN = 240


def _norm(subject: str) -> str:
    return "".join(c for c in subject.lower() if c.isalnum() or c == " ").strip()


class SupportTriageAdapter:
    name = "example_support_triage"
    title = "Support ticket triage (example)"
    scan_keywords = ["scan", "triage", "backlog", "any issues"]
    specialists = [
        SpecialistSpec(
            role="deduplication",
            title="Deduplication",
            description="Finds tickets the same customer opened twice for one problem.",
            finding_types=["duplicate_ticket"],
            keywords=["duplicate", "twice", "same ticket"],
        ),
        SpecialistSpec(
            role="sla_watch",
            title="SLA watch",
            description="Flags first responses that missed the SLA.",
            finding_types=["sla_breach"],
            keywords=["sla", "response", "late", "waiting"],
        ),
    ]

    async def resolve_scope(self, question: str | None, tools: ToolBox) -> Scope:
        return Scope(date_from=date(2026, 6, 1), date_to=date(2026, 6, 3))

    async def run_checks(self, role: str, tools: ToolBox, scope: Scope) -> list[Finding]:
        out: list[Finding] = []
        if role == "deduplication":
            seen: dict[tuple[str, str], str] = {}
            for tid, cust, subject, *_ in TICKETS:
                key = (cust, _norm(subject))
                if key in seen:
                    out.append(
                        Finding(
                            finding_type="duplicate_ticket",
                            specialist=role,
                            subject=tid,
                            title=f"{tid} duplicates {seen[key]}",
                            affected_records=1,
                            evidence=[
                                Evidence(
                                    source="tickets", summary=f"same customer {cust}, same subject"
                                )
                            ],
                        )
                    )
                else:
                    seen[key] = tid
        elif role == "sla_watch":
            for tid, _, _, opened, responded in TICKETS:
                wait = (
                    datetime.fromisoformat(responded) - datetime.fromisoformat(opened)
                ).seconds // 60
                if wait > FIRST_RESPONSE_SLA_MIN:
                    out.append(
                        Finding(
                            finding_type="sla_breach",
                            specialist=role,
                            subject=tid,
                            title=f"{tid} waited {wait} minutes for a first response",
                            affected_records=1,
                            metrics={"wait_minutes": wait},
                        )
                    )
        else:
            raise ValueError(f"unknown specialist {role}")
        for f in out:
            f.severity = self.severity(f)
        return out

    async def overview(self, tools: ToolBox) -> dict[str, Any]:
        return {"as_of": "2026-06-03", "volume": None, "last_run": None, "tickets": len(TICKETS)}

    def severity(self, finding: Finding) -> Severity:
        return "S2" if finding.finding_type == "sla_breach" else "S4"

    def problem_statement(self, finding: Finding) -> str:
        return finding.title

    def retrieval_query(self, finding: Finding) -> str:
        return finding.finding_type.replace("_", " ")

    def fallback_analysis(self, finding: Finding, sources: list[RetrievedChunk]) -> FindingAnalysis:
        if finding.finding_type == "duplicate_ticket":
            return FindingAnalysis(
                root_cause_hypothesis=(
                    "The customer resubmitted because the first ticket showed no acknowledgement."
                ),
                recommended_fix=["Merge the tickets and reply on the original thread."],
                confidence=0.7,
            )
        return FindingAnalysis(
            root_cause_hypothesis="The queue had no owner during the gap between shifts.",
            recommended_fix=["Assign an owner and reply now.", "Review shift handover coverage."],
            confidence=0.5,
        )
