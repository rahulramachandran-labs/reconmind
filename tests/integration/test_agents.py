import asyncio
import json
import time
import uuid

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.config import ROOT, Settings
from app.domain.retail_recon import RetailReconAdapter
from tests.fakes import ScriptedProvider, well_behaved
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
    assert reports and all(r["analysis_by"] == "scripted" for r in reports)
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
