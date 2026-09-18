"""Periodic scans inside the API process."""

import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.agents.service import InvestigationService

log = logging.getLogger(__name__)


async def scheduled_scan(service: InvestigationService) -> None:
    events = await service.run_to_end(service.run("scan"))
    last = events[-1] if events else {}
    log.info(
        "scheduled scan finished", extra={"outcome": last.get("type"), "run_id": last.get("run_id")}
    )


def start_scheduler(service: InvestigationService, minutes: int) -> Any:
    if minutes <= 0:
        return None
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        scheduled_scan,
        "interval",
        minutes=minutes,
        args=[service],
        id="pipeline-scan",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info("scan scheduler started", extra={"every_minutes": minutes})
    return scheduler
