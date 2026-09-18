"""The agent layer must not know which business it is working for."""

import ast
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from app.agents.llm import TracedLLM
from app.agents.nodes import AgentDeps
from app.agents.service import InvestigationService
from app.agents.store import MemoryRunStore
from app.config import ROOT, Settings
from app.domain.example_support_triage import SupportTriageAdapter
from app.llm import LLMChain
from app.retrieval.service import RetrievalService


class NoTools:
    async def call(self, server: str, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("the support adapter needs no tools")


async def test_graph_boots_and_runs_on_the_stub_adapter(settings: Settings) -> None:
    store = MemoryRunStore()
    deps = AgentDeps(
        adapter=SupportTriageAdapter(),
        tools=NoTools(),
        retrieval=RetrievalService.from_settings(settings),
        llm=TracedLLM(LLMChain([])),
        store=store,
    )
    svc = InvestigationService(deps, store, InMemorySaver())
    assert {"deduplication", "sla_watch"} <= set(svc.graph.get_graph().nodes)
    events = await svc.run_to_end(svc.run("scan"))
    findings = {(e["finding_type"], e["specialist"]) for e in events if e["type"] == "finding"}
    assert findings == {("duplicate_ticket", "deduplication"), ("sla_breach", "sla_watch")}
    # the low-confidence SLA finding goes to human review, same as in the retail domain
    paused = events[-1]
    assert paused["type"] == "paused" and [r["title"] for r in paused["reports"]] == [
        "T-103 waited 390 minutes for a first response"
    ]
    assert {r["finding_type"] for r in store.reports.values()} == {"duplicate_ticket", "sla_breach"}


def test_agent_layer_imports_only_the_protocol() -> None:
    for path in sorted((ROOT / "app" / "agents").glob("*.py")):
        tree = ast.parse(Path(path).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("app.domain.retail_recon"), path.name
                assert not node.module.startswith("app.domain.example_support_triage"), path.name
        assert "retail" not in path.read_text().lower().replace(
            "app.domain.registry", ""
        ), path.name
