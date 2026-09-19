"""What every agent node receives: the domain adapter, tools, retrieval, the
traced model client and the run store."""

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.agents.schemas import IncidentReport
from app.domain.protocol import DomainAdapter, ToolBox
from app.llm.traced import TracedLLM
from app.observability.tracer import current_tracer
from app.retrieval.service import RetrievalService
from app.retrieval.types import RetrievedChunk


class RunStore(Protocol):
    """The part of the run store the nodes write to."""

    def save_plan(self, run_id: uuid.UUID, plan: dict[str, Any]) -> None: ...
    def save_reports(
        self, run_id: uuid.UUID, reports: list[IncidentReport]
    ) -> list[IncidentReport]: ...
    def apply_decisions(
        self, run_id: uuid.UUID, decisions: dict[str, dict[str, Any]]
    ) -> list[dict[str, Any]]: ...


@dataclass
class AgentDeps:
    adapter: DomainAdapter
    tools: ToolBox
    retrieval: RetrievalService
    llm: TracedLLM
    store: RunStore
    planner_threshold: float = 0.5
    review_threshold: float = 0.6
    retrieval_k: int = 4
    extra: dict[str, Any] = field(default_factory=dict)


def traced_search(retrieval: RetrievalService, query: str, k: int) -> list[RetrievedChunk]:
    """Retrieval inside a run, recorded as a trace step."""
    start = time.perf_counter()
    hits = retrieval.search(query, k)
    tracer = current_tracer()
    if tracer:
        tracer.record(
            kind="retrieval",
            name=f"{retrieval.mode} search",
            input={"query": query, "k": k},
            output={"chunks": [h.chunk_id for h in hits]},
            latency_ms=int((time.perf_counter() - start) * 1000),
        )
    return hits
