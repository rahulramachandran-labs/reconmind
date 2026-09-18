"""The contract between the agent layer and a business domain.

Everything that knows what a "transaction" or an "outlet" is lives behind this
protocol. The agents only see findings, severities and text.
"""

from datetime import date
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.retrieval.types import RetrievedChunk

Severity = Literal["S1", "S2", "S3", "S4"]
SEVERITY_ORDER: dict[str, int] = {"S1": 1, "S2": 2, "S3": 3, "S4": 4}


class Evidence(BaseModel):
    source: str = Field(description="e.g. mcp:warehouse-metadata/run_check or a doc id")
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class Finding(BaseModel):
    """Facts established by deterministic checks. No model output in here."""

    finding_type: str
    specialist: str
    subject: str
    title: str
    affected_records: int
    affected_rate: float | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    severity: Severity = "S3"


class FindingAnalysis(BaseModel):
    """What a model (or the adapter's template) says about a finding."""

    root_cause_hypothesis: str = Field(min_length=20, max_length=1200)
    recommended_fix: list[str] = Field(min_length=1, max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)
    open_questions: list[str] = Field(default_factory=list, max_length=6)


class Scope(BaseModel):
    date_from: date
    date_to: date


class SpecialistSpec(BaseModel):
    role: str = Field(pattern=r"^[a-z_]{3,40}$")
    title: str
    description: str
    finding_types: list[str]
    keywords: list[str]


class ToolBox(Protocol):
    async def call(self, server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]: ...


class DomainAdapter(Protocol):
    name: str
    title: str
    specialists: list[SpecialistSpec]
    scan_keywords: list[str]

    async def resolve_scope(self, question: str | None, tools: ToolBox) -> Scope: ...

    async def run_checks(self, role: str, tools: ToolBox, scope: Scope) -> list[Finding]: ...

    def severity(self, finding: Finding) -> Severity: ...

    def problem_statement(self, finding: Finding) -> str: ...

    def retrieval_query(self, finding: Finding) -> str: ...

    def fallback_analysis(
        self, finding: Finding, sources: list[RetrievedChunk]
    ) -> FindingAnalysis: ...
