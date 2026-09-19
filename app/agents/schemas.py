from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.protocol import Evidence, Severity


class PlannerDecision(BaseModel):
    intent: Literal["investigate", "answer", "unclear"]
    specialists: list[str] = Field(default_factory=list, max_length=6)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=3, max_length=400)


class SourceRef(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    section: str


class AffectedRecords(BaseModel):
    count: int
    rate: float | None = None
    detail: str


class IncidentReport(BaseModel):
    """What a person reads: modelled on a change request, not an agent transcript."""

    id: UUID
    run_id: UUID
    finding_type: str
    specialist: str
    severity: Severity
    title: str
    problem_statement: str
    affected_records: AffectedRecords
    root_cause_hypothesis: str
    recommended_fix: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_label: Literal["low", "medium", "high"]
    open_questions: list[str]
    evidence: list[Evidence]
    sources: list[SourceRef]
    analysis_by: str
    needs_review: bool
    review_reason: str | None = None
    trace_url: str | None = None
    status: Literal["pending_review", "published", "rejected"] = "published"
    review_note: str | None = None
    seen_count: int = 1
    repeat: bool = Field(
        default=False, description="Already reported by an earlier scan; not written up again"
    )

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.finding_type, self.title)


class RunSummary(BaseModel):
    headline: str = Field(min_length=5, max_length=200)
    summary: str = Field(min_length=10, max_length=1500)


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reject", "annotate"]
    note: str | None = Field(default=None, max_length=2000)
    reviewer: str = Field(default="reviewer", max_length=120)


def fingerprint(finding_type: str, title: str) -> str:
    """Titles carry the subject and the size (file, location, row counts), so a
    finding with the same type and title is the same finding seen again."""
    return f"{finding_type}:{title}"


def confidence_label(c: float) -> Literal["low", "medium", "high"]:
    return "high" if c >= 0.75 else "medium" if c >= 0.5 else "low"
