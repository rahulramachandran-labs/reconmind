from mcp import Client

from mcp_servers.orchestration_metadata.server import build_server


async def test_tools_are_listed_and_read_only() -> None:
    async with Client(build_server()) as c:
        names = {t.name for t in (await c.list_tools()).tools}
    assert names == {"list_dag_runs", "get_task_log", "get_timing_history", "get_failed_tasks"}


async def test_failed_task_and_its_log() -> None:
    async with Client(build_server()) as c:
        failed = (await c.call_tool("get_failed_tasks", {})).structured_content
        assert [f["task_id"] for f in failed["failures"]] == ["validate_schema"]
        f = failed["failures"][0]
        assert "ContractViolation" in f["first_error_line"]
        log = (
            await c.call_tool("get_task_log", {"run_id": f["run_id"], "task_id": "validate_schema"})
        ).structured_content
        assert log["state"] == "failed" and any("basket_ref" in line for line in log["log"])


async def test_timing_history_shows_the_slow_sensor() -> None:
    async with Client(build_server()) as c:
        res = (
            await c.call_tool("get_timing_history", {"dag_id": "retail_txn_daily"})
        ).structured_content
    sensor = next(t for t in res["tasks"] if t["task_id"] == "wait_for_submitter_files")
    slow = max(sensor["history"], key=lambda h: h["duration_s"])
    assert slow["business_date"] == "2026-06-18" and slow["duration_s"] > 20 * sensor["median_s"]


async def test_runs_since_a_date() -> None:
    async with Client(build_server()) as c:
        res = (
            await c.call_tool(
                "list_dag_runs", {"dag_id": "retail_txn_daily", "since": "2026-06-20"}
            )
        ).structured_content
    assert [r["business_date"] for r in res["runs"]] == ["2026-06-20", "2026-06-21"]


async def test_inputs_are_validated() -> None:
    async with Client(build_server()) as c:
        bad_dag = await c.call_tool("list_dag_runs", {"dag_id": "Robert'); drop table"})
        assert bad_dag.is_error
        unknown = await c.call_tool("list_dag_runs", {"dag_id": "some_other_dag"})
        assert unknown.is_error
        bad_date = await c.call_tool("get_failed_tasks", {"since": "last tuesday"})
        assert bad_date.is_error
        missing = await c.call_tool(
            "get_task_log", {"run_id": "nope", "task_id": "validate_schema"}
        )
        assert missing.is_error
