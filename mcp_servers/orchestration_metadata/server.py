"""orchestration-metadata: DAG runs, task logs, timings and failures.

Reads the orchestrator's run history (an Airflow-style JSON export here) and
exposes it read-only.
"""

import json
import os
from pathlib import Path
from statistics import median
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field

from mcp_servers.common import Identifier, IsoDate

ROOT = Path(__file__).resolve().parents[2]
DagId = Annotated[str, Field(pattern=r"^[a-z0-9_]{1,64}$")]


class DagRun(BaseModel):
    run_id: str
    business_date: str
    state: str
    start: str
    end: str
    duration_s: int
    failed_tasks: list[str]


class DagRuns(BaseModel):
    dag_id: str
    runs: list[DagRun]


class TaskLog(BaseModel):
    run_id: str
    task_id: str
    state: str
    try_number: int
    start: str | None
    end: str | None
    duration_s: int | None
    log: list[str]


class TaskTiming(BaseModel):
    task_id: str
    median_s: float
    history: list[dict[str, Any]]


class TimingHistory(BaseModel):
    dag_id: str
    tasks: list[TaskTiming]


class FailedTask(BaseModel):
    run_id: str
    business_date: str
    task_id: str
    state: str
    first_error_line: str


class FailedTasks(BaseModel):
    failures: list[FailedTask]


def _secs(start: str, end: str) -> int:
    from datetime import datetime

    return int(
        (
            datetime.fromisoformat(end.replace("Z", "+00:00"))
            - datetime.fromisoformat(start.replace("Z", "+00:00"))
        ).total_seconds()
    )


def build_server(runs_path: Path | None = None) -> MCPServer:
    server = MCPServer(
        "orchestration-metadata",
        instructions=(
            "Read-only run history for the retail_txn_daily DAG: runs, task logs, "
            "per-task timing history and failed tasks."
        ),
    )

    def load() -> dict[str, Any]:
        path = runs_path or Path(
            os.environ.get("DAG_RUNS_PATH", ROOT / "data" / "sample" / "airflow" / "dag_runs.json")
        )
        return json.loads(path.read_text())

    def runs_for(dag_id: str) -> list[dict[str, Any]]:
        data = load()
        if data["dag_id"] != dag_id:
            raise ValueError(f"unknown dag {dag_id}")
        return list(data["runs"])

    @server.tool(
        description="Runs of a DAG, optionally only those for business dates on or after `since`."
    )
    def list_dag_runs(dag_id: DagId, since: IsoDate | None = None) -> DagRuns:
        out = []
        for r in runs_for(dag_id):
            if since and r["business_date"] < since:
                continue
            out.append(
                DagRun(
                    run_id=r["run_id"],
                    business_date=r["business_date"],
                    state=r["state"],
                    start=r["start"],
                    end=r["end"],
                    duration_s=_secs(r["start"], r["end"]),
                    failed_tasks=[t["task_id"] for t in r["tasks"] if t["state"] == "failed"],
                )
            )
        return DagRuns(dag_id=dag_id, runs=out)

    @server.tool(description="State, timing and log lines for one task in one run.")
    def get_task_log(run_id: Identifier, task_id: DagId) -> TaskLog:
        for r in load()["runs"]:
            if r["run_id"] == run_id:
                for t in r["tasks"]:
                    if t["task_id"] == task_id:
                        return TaskLog(
                            run_id=run_id,
                            **{k: t[k] for k in TaskLog.model_fields if k != "run_id"},
                        )
        raise ValueError(f"no task {task_id} in run {run_id}")

    @server.tool(description="Per-task duration history and median for a DAG.")
    def get_timing_history(dag_id: DagId) -> TimingHistory:
        by_task: dict[str, list[dict[str, Any]]] = {}
        for r in runs_for(dag_id):
            for t in r["tasks"]:
                by_task.setdefault(t["task_id"], []).append(
                    {
                        "business_date": r["business_date"],
                        "duration_s": t["duration_s"],
                        "state": t["state"],
                    }
                )
        tasks = []
        for task_id, hist in by_task.items():
            done = [h["duration_s"] for h in hist if h["duration_s"] is not None]
            tasks.append(
                TaskTiming(
                    task_id=task_id, median_s=float(median(done)) if done else 0.0, history=hist
                )
            )
        return TimingHistory(dag_id=dag_id, tasks=tasks)

    @server.tool(
        description="Tasks that ended in state failed, for business dates on or after `since`."
    )
    def get_failed_tasks(since: IsoDate | None = None) -> FailedTasks:
        out = []
        for r in load()["runs"]:
            if since and r["business_date"] < since:
                continue
            for t in r["tasks"]:
                if t["state"] == "failed":
                    errors = [line for line in t["log"] if "Error" in line or "Violation" in line]
                    out.append(
                        FailedTask(
                            run_id=r["run_id"],
                            business_date=r["business_date"],
                            task_id=t["task_id"],
                            state=t["state"],
                            first_error_line=(errors or t["log"] or [""])[0],
                        )
                    )
        return FailedTasks(failures=out)

    return server
