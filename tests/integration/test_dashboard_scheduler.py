import asyncio
from datetime import UTC, datetime

from sqlalchemy.engine import Engine

from app.agents.scheduler import scheduled_scan, start_scheduler
from app.core.config import Settings
from tests.integration.agent_fixtures import retail_service


async def test_overview_uses_the_latest_business_date(
    loaded_engine: Engine, settings: Settings
) -> None:
    async with retail_service(loaded_engine, settings) as svc:
        o = await svc.deps.adapter.overview(svc.deps.tools)
    assert o["as_of"] == "2026-06-21"
    assert len(o["volume"]["series"]) == 14
    assert o["volume"]["rows"] == o["volume"]["series"][-1]["rows"] > 0
    light = next(s for s in o["volume"]["series"] if s["date"] == "2026-06-18")
    assert light["by_submitter"]["S1001"] == 110
    assert o["last_run"]["state"] == "success" and o["last_run"]["runs_failed_14d"] == 1


async def test_scheduled_scan_feeds_the_dashboard_numbers(
    loaded_engine: Engine, settings: Settings
) -> None:
    async with retail_service(loaded_engine, settings) as svc:
        await scheduled_scan(svc)
        usage = svc.store.usage_on(datetime.now(UTC).date())
        findings = svc.store.open_findings()
    assert usage["runs"] >= 1 and usage["last_scan"]["status"] == "paused_review"
    assert findings["by_severity"] == {"S1": 1, "S2": 3, "S3": 0, "S4": 0}
    assert findings["pending_review"] >= 1


async def test_scheduler_is_off_at_zero_and_on_otherwise(
    loaded_engine: Engine, settings: Settings
) -> None:
    async with retail_service(loaded_engine, settings) as svc:
        assert start_scheduler(svc, 0) is None
        sched = start_scheduler(svc, 15)
        try:
            job = sched.get_job("pipeline-scan")
            assert job.trigger.interval.total_seconds() == 900
            assert job.max_instances == 1
        finally:
            sched.shutdown(wait=False)
            await asyncio.sleep(0)
