import asyncio
import json
import time
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.agents.service import NoModelWriteUp, UnknownIncident
from app.core.config import ROOT, Settings
from app.domain.retail_recon import RetailReconAdapter
from app.llm.providers import Message
from tests.fakes import ScriptedProvider, ScriptedToolProvider, well_behaved
from tests.integration.agent_fixtures import retail_service

EXPECTED = json.loads((ROOT / "data" / "sample" / "expected_anomalies.json").read_text())
PLANTED = {
    (k, v["expected_severity"], v["expected_agent"]) for k, v in EXPECTED.items() if k != "summary"
}


async def test_scan_finds_every_planted_anomaly(loaded_engine: Engine, settings: Settings) -> None:
    async with retail_service(loaded_engine, settings) as svc:
        events = await svc.run_to_end(svc.run("scan"))
    found = {
        (e["finding_type"], e["severity"], e["specialist"])
        for e in events
        if e["type"] == "finding"
    }
    assert found == PLANTED
    paused = next(e for e in events if e["type"] == "paused")
    assert paused["kind"] == "reports"
    assert [r["severity"] for r in paused["reports"]] == ["S1"]
    run_id = uuid.UUID(paused["run_id"])
    run = svc.store.get_run(run_id)
    assert run["status"] == "paused_review"
    kinds = {s["kind"] for s in run["steps"]}
    assert {"node", "tool", "retrieval"} <= kinds
    tools_used = {s["name"] for s in run["steps"] if s["kind"] == "tool"}
    assert "warehouse-metadata/run_check" in tools_used
    assert "orchestration-metadata/get_failed_tasks" in tools_used
    statuses = sorted(r["status"] for r in run["reports"])
    assert statuses == ["pending_review", "published", "published", "published"]


async def test_approving_the_review_resumes_and_writes_the_ledger(
    loaded_engine: Engine, settings: Settings
) -> None:
    async with retail_service(loaded_engine, settings) as svc:
        events = await svc.run_to_end(svc.run("scan"))
        paused = next(e for e in events if e["type"] == "paused")
        report_id = uuid.UUID(paused["reports"][0]["id"])
        run_id = svc.store.record_decision(report_id, "annotate", "resend requested", "rahul")
        decided, remaining = svc.store.pending_decisions(run_id)
        assert remaining == 0
        after = await svc.run_to_end(svc.resume(run_id, decided))
    assert after[-1]["type"] == "done"
    assert svc.store.get_incident(report_id)["status"] == "published"
    assert svc.store.get_incident(report_id)["review_note"] == "resend requested"
    assert svc.store.get_run_row(run_id)["status"] == "completed"
    with loaded_engine.connect() as conn:
        actions = conn.execute(
            text("select action, actor from audit_ledger where subject = :s order by id"),
            {"s": str(report_id)},
        ).all()
    assert [tuple(a) for a in actions] == [
        ("finding.created", "agent:data_quality"),
        ("review.annotated", "human:rahul"),
    ]


async def test_rejecting_a_finding(loaded_engine: Engine, settings: Settings) -> None:
    async with retail_service(loaded_engine, settings) as svc:
        events = await svc.run_to_end(svc.run("scan"))
        paused = next(e for e in events if e["type"] == "paused")
        report_id = uuid.UUID(paused["reports"][0]["id"])
        run_id = svc.store.record_decision(report_id, "reject", "known issue", "rahul")
        await svc.run_to_end(svc.resume(run_id, svc.store.pending_decisions(run_id)[0]))
    assert svc.store.get_incident(report_id)["status"] == "rejected"
    assert svc.store.record_decision(report_id, "approve", None, "x") is None


async def test_knowledge_questions_go_straight_to_the_runbooks(
    loaded_engine: Engine, settings: Settings
) -> None:
    async with retail_service(loaded_engine, settings) as svc:
        events = await svc.run_to_end(
            svc.run("question", "which file wins when a submitter resends?")
        )
    types = [e["type"] for e in events]
    assert "finding" not in types and types[-1] == "done"
    answer = next(e for e in events if e["type"] == "answer")
    assert answer["provider"] == "extractive" and answer["sources"]


async def test_every_llm_call_is_traced(loaded_engine: Engine, settings: Settings) -> None:
    provider = ScriptedProvider(well_behaved)
    async with retail_service(loaded_engine, settings, [provider]) as svc:
        events = await svc.run_to_end(
            svc.run("question", "are there any duplicate submissions this week?")
        )
        run_id = uuid.UUID(events[0]["run_id"])
        steps = svc.store.get_run(run_id)["steps"]
    llm_steps = [s for s in steps if s["kind"] == "llm"]
    assert len(provider.calls) == len(llm_steps) > 0
    assert all(s["prompt_version"] and s["provider"] == "scripted" for s in llm_steps)
    plan = next(e for e in events if e["type"] == "plan")
    assert plan["planned_by"] == "scripted"
    assert plan["specialists"] == ["reconciliation"], "invented specialists are dropped"
    reports = [e for e in events if e["type"] == "report"]
    assert reports and all(
        r["analysis_by"] == "model" and r["model_analysis"]["provider"] == "scripted"
        for r in reports
    )
    assert all(r["template"]["root_cause_hypothesis"] for r in reports), "the template is kept"
    drift = next(r for r in reports if r["finding_type"] == "key_drift")
    assert drift["confidence"] <= 0.75, "model confidence is capped at the prior plus 0.15"


async def test_specialists_run_concurrently(loaded_engine: Engine, settings: Settings) -> None:
    class Slow(RetailReconAdapter):
        async def run_checks(self, role, tools, scope):  # type: ignore[no-untyped-def]
            await asyncio.sleep(0.6)
            return []

    async with retail_service(loaded_engine, settings, adapter=Slow()) as svc:
        start = time.perf_counter()
        await svc.run_to_end(svc.run("scan"))
        elapsed = time.perf_counter() - start
    assert elapsed < 1.1, f"two 0.6 s specialists took {elapsed:.2f}s"


async def test_a_second_scan_does_not_duplicate_findings(
    loaded_engine: Engine, settings: Settings
) -> None:
    async with retail_service(loaded_engine, settings) as svc:
        first = await svc.run_to_end(svc.run("scan"))
        second = await svc.run_to_end(svc.run("scan"))
        ids_first = {e["id"] for e in first if e["type"] == "report"}
        repeats = [e for e in second if e["type"] == "report"]
        assert {e["id"] for e in repeats} == ids_first
        assert all(e["repeat"] and e["seen_count"] == 2 for e in repeats)
        assert (
            second[-1]["type"] == "done"
        ), "the S1 is already waiting; the second scan must not pause"
        summary = next(e for e in second if e["type"] == "summary")
        assert "0 new" in summary["headline"]
        assert len(svc.store.list_incidents()) == 4
        assert svc.store.open_findings()["by_severity"] == {"S1": 1, "S2": 3, "S3": 0, "S4": 0}
        assert len(svc.store.list_incidents(status="pending_review")) == 1
    with loaded_engine.connect() as conn:
        seen = conn.scalar(
            text("select count(*) from audit_ledger where action = 'finding.seen_again'")
        )
    assert seen >= 4


async def test_a_rejected_finding_stays_rejected_on_rescan(
    loaded_engine: Engine, settings: Settings
) -> None:
    async with retail_service(loaded_engine, settings) as svc:
        events = await svc.run_to_end(svc.run("scan"))
        paused = next(e for e in events if e["type"] == "paused")
        report_id = uuid.UUID(paused["reports"][0]["id"])
        run_id = svc.store.record_decision(report_id, "reject", "known, resend on its way", "rahul")
        await svc.run_to_end(svc.resume(run_id, svc.store.pending_decisions(run_id)[0]))
        again = await svc.run_to_end(svc.run("scan"))
        s1 = next(e for e in again if e["type"] == "report" and e["severity"] == "S1")
        assert s1["repeat"] and s1["status"] == "rejected"
        assert again[-1]["type"] == "done"
        assert svc.store.open_findings()["by_severity"]["S1"] == 0


async def test_regenerate_writes_a_model_version_beside_the_template(
    loaded_engine: Engine, settings: Settings
) -> None:
    model_up = {"on": False}

    def respond(system: str, messages: list[Message]) -> str:
        return well_behaved(system, messages) if model_up["on"] else "not json at all"

    async with retail_service(loaded_engine, settings, [ScriptedProvider(respond)]) as svc:
        await svc.run_to_end(svc.run("scan"))
        drift = next(r for r in svc.store.list_incidents() if r["finding_type"] == "key_drift")
        assert drift["analysis_by"] == "template" and drift["model_analysis"] is None
        model_up["on"] = True
        out = await svc.regenerate(uuid.UUID(drift["id"]), "rahul")
        regen = next(r for r in svc.store.list_runs() if r["trigger"] == "regenerate")
    model, template = out["model_analysis"], out["template"]
    assert out["analysis_by"] == "model"
    assert (model["provider"], model["model"]) == ("scripted", "fake-1")
    assert model["prompt_tokens"] == 100 and model["cost_usd"] == 0.0001 and model["latency_ms"] > 0
    assert out["root_cause_hypothesis"] == model["root_cause_hypothesis"]
    assert model["root_cause_hypothesis"] != template["root_cause_hypothesis"]
    # the facts are the checks', in both versions
    assert model["problem_statement"] == template["problem_statement"] == out["problem_statement"]
    assert out["affected_records"] == drift["affected_records"]
    assert out["confidence"] <= 0.75, "still capped at the template's confidence plus 0.15"
    assert regen["status"] == "completed" and regen["llm_calls"] >= 1
    with loaded_engine.connect() as conn:
        actor = conn.scalar(
            text("select actor from audit_ledger where action = 'finding.rewritten'")
        )
    assert actor == "human:rahul"


async def test_regenerate_without_a_model_keeps_the_template(
    loaded_engine: Engine, settings: Settings
) -> None:
    async with retail_service(loaded_engine, settings) as svc:
        await svc.run_to_end(svc.run("scan"))
        report = svc.store.list_incidents()[0]
        with pytest.raises(NoModelWriteUp):
            await svc.regenerate(uuid.UUID(report["id"]), "rahul")
        with pytest.raises(UnknownIncident):
            await svc.regenerate(uuid.uuid4(), "rahul")
        assert svc.store.get_incident(uuid.UUID(report["id"]))["analysis_by"] == "template"


async def test_the_planner_sees_the_conversation_it_follows(
    loaded_engine: Engine, settings: Settings
) -> None:
    provider = ScriptedProvider(well_behaved)
    history = [
        {"role": "user", "content": "Which file wins when a submitter resends the same day?"},
        {"role": "assistant", "content": "The later file wins [1]."},
    ]
    async with retail_service(loaded_engine, settings, [provider]) as svc:
        await svc.run_to_end(
            svc.run("question", "What should we look at before reprocessing it?", history)
        )
    planner_prompt = next(m for s, m in provider.calls if "route questions" in s)[-1].content
    assert "Earlier in this conversation" in planner_prompt
    assert "Which file wins when a submitter resends" in planner_prompt


async def test_a_rescan_writes_up_only_what_needs_it(
    loaded_engine: Engine, settings: Settings
) -> None:
    model_up = {"on": False}

    def respond(system: str, messages: list[Message]) -> str:
        return well_behaved(system, messages) if model_up["on"] else "not json at all"

    provider = ScriptedProvider(respond)
    count = text("select count(*) from audit_ledger where action = 'finding.rewritten'")
    with loaded_engine.connect() as conn:
        rewritten_before = conn.scalar(count)
    async with retail_service(loaded_engine, settings, [provider]) as svc:
        await svc.run_to_end(svc.run("scan"))
        assert all(r["model_analysis"] is None for r in svc.store.list_incidents())

        # the model is back: the template-only write-ups are replaced on the next scan
        model_up["on"] = True
        await svc.run_to_end(svc.run("scan"))
        upgraded = svc.store.list_incidents()
        assert all(r["analysis_by"] == "model" and r["model_analysis"] for r in upgraded)
        assert all(r["template"]["root_cause_hypothesis"] for r in upgraded)

        # and once written up, a finding costs no more analysis calls
        before = len(provider.calls)
        await svc.run_to_end(svc.run("scan"))
        analyses = [s for s, _ in provider.calls[before:] if "writing up an incident" in s]
        assert analyses == []
    with loaded_engine.connect() as conn:
        assert conn.scalar(count) - rewritten_before == 4  # the ledger is append-only


def _routes_to_explore(system: str, messages: list[Message]) -> str:
    if "route questions" in system:
        return json.dumps(
            {"intent": "explore", "specialists": [], "confidence": 0.8, "rationale": "a fact"}
        )
    return well_behaved(system, messages)


async def test_the_explorer_answers_from_the_tools_it_chose(
    loaded_engine: Engine, settings: Settings
) -> None:
    provider = ScriptedToolProvider(
        _routes_to_explore,
        plan=[("warehouse__get_table_stats", {"table": "transactions", "date": "2026-06-18"})],
        answer="S1001 sent 110 rows on 2026-06-18, per warehouse__get_table_stats.",
    )
    async with retail_service(loaded_engine, settings, [provider]) as svc:
        events = await svc.run_to_end(
            svc.run("question", "Which submitter sent the fewest rows on 2026-06-18?")
        )
        steps = svc.store.get_run(uuid.UUID(events[0]["run_id"]))["steps"]
    assert next(e for e in events if e["type"] == "plan")["intent"] == "explore"
    answer = next(e for e in events if e["type"] == "answer")
    assert answer["text"].startswith("S1001") and answer["model"] == "fake-1"
    assert "warehouse-metadata/get_table_stats" in [s["name"] for s in steps if s["kind"] == "tool"]
    assert [s["name"] for s in steps if s["name"].startswith("explore")] == [
        "explore",
        "explore#1",
        "explore",
    ], "two model turns, then the explore node itself"
    # what the tool returned went back to the model
    last = provider.tool_turns[-1][0]
    assert any(m["role"] == "tool" and "S1001_20260618" in str(m["content"]) for m in last)


async def test_the_explorer_stops_after_three_tool_calls(
    loaded_engine: Engine, settings: Settings
) -> None:
    provider = ScriptedToolProvider(
        _routes_to_explore,
        plan=[("orchestration__list_dag_runs", {"dag_id": "retail_txn_daily"})] * 5
        + [("nowhere__nothing", {})],
        answer="Done looking.",
    )
    async with retail_service(loaded_engine, settings, [provider]) as svc:
        events = await svc.run_to_end(
            svc.run("question", "Show me the slowest night on 2026-06-18")
        )
        steps = svc.store.get_run(uuid.UUID(events[0]["run_id"]))["steps"]
    assert sum(1 for s in steps if s["kind"] == "tool" and "list_dag_runs" in s["name"]) == 1 + 3
    assert provider.tool_turns[-1][1] == [], "the last turn offers no tools"
    assert next(e for e in events if e["type"] == "answer")["text"] == "Done looking."
