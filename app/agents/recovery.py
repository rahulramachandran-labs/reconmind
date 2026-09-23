"""Runs left behind by a process that stopped.

A deploy, an out-of-memory kill or a free instance going to sleep ends the
process mid-run. The row stays `running` for good, so the dashboard reports a
scan nobody is running and the run never reaches a terminal state. Nothing can
still be in flight while this process is starting, so anything still `running`
belonged to a process that is gone.

Runs waiting for a person (`paused_plan`, `paused_review`) are left exactly as
they are. Their state is a LangGraph checkpoint in Postgres, a decision resumes
them hours or days later, and surviving a restart is the point of the queue.
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.engine import Engine

from app.db.models import AgentRun
from app.db.session import session_scope

log = logging.getLogger("reconmind")
REASON = "the process running it stopped before it finished"


def interrupt_orphans(engine: Engine) -> int:
    """Mark runs a dead process left in flight, and say how many there were."""
    with session_scope(engine) as s:
        done = s.execute(
            update(AgentRun)
            .where(AgentRun.status == "running")
            .values(status="interrupted", error=REASON, finished_at=datetime.now(UTC))
        )
    count = int(getattr(done, "rowcount", 0) or 0)
    if count:
        log.warning("runs left in flight by an earlier process", extra={"interrupted": count})
    return count
