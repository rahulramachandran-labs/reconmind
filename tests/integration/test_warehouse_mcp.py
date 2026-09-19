import json

import pytest
from mcp import Client
from sqlalchemy.engine import Engine

from app.core.config import ROOT
from mcp_servers.warehouse_metadata.server import build_server

EXPECTED = json.loads((ROOT / "data" / "sample" / "expected_anomalies.json").read_text())


@pytest.fixture
def server(loaded_engine: Engine):  # type: ignore[no-untyped-def]
    return build_server(loaded_engine)


async def test_list_tables_and_schema(server) -> None:  # type: ignore[no-untyped-def]
    async with Client(server) as c:
        tables = (await c.call_tool("list_tables", {})).structured_content["tables"]
        by = {t["name"]: t["row_count"] for t in tables}
        assert by["transactions"] == EXPECTED["summary"]["rows"] and by["file_loads"] == 85
        schema = (
            await c.call_tool("get_table_schema", {"table": "transactions"})
        ).structured_content
        assert "channel_basket_id" in {col["name"] for col in schema["contract"]}


async def test_checks_return_the_planted_numbers(server) -> None:  # type: ignore[no-untyped-def]
    args = {"date_from": "2026-06-01", "date_to": "2026-06-21"}
    async with Client(server) as c:
        dup = (
            await c.call_tool("run_check", {"check": "duplicate_keys", **args})
        ).structured_content
        drift = (await c.call_tool("run_check", {"check": "key_drift", **args})).structured_content
    d = EXPECTED["duplicate_submission"]
    assert dup["groups"] == [
        {
            "winning_file": d["resend_file"],
            "superseded_file": d["original_file"],
            "business_date": d["business_date"],
            "superseded_rows": d["superseded_rows"],
            "changed_rows": d["changed_rows"],
        }
    ]
    k = EXPECTED["key_drift"]
    assert drift["rows_in_window"] == k["rows_in_window"]
    assert [(g["location_id"], g["reported_outlet_id"], g["rows"]) for g in drift["groups"]] == [
        (k["location_id"], k["drifted_outlet_id"], k["drifted_rows"])
    ]


async def test_table_stats_expose_the_renamed_header(server) -> None:  # type: ignore[no-untyped-def]
    sd = EXPECTED["schema_drift"]
    async with Client(server) as c:
        stats = (
            await c.call_tool(
                "get_table_stats", {"table": "transactions", "date": sd["business_date"]}
            )
        ).structured_content
        registry = (
            await c.call_tool(
                "get_table_stats", {"table": "submitter_registry", "date": "2026-06-01"}
            )
        ).structured_content
    f = next(f for f in stats["files"] if f["file_name"] == sd["file"])
    assert f["missing_columns"] == ["channel_basket_id"] and f["unexpected_columns"] == [
        "basket_ref"
    ]
    assert f["null_counts"] == {"channel_basket_id": sd["affected_rows"]}
    assert {r["submitter_id"] for r in registry["rows"]} == {"S1001", "S1002", "S1003", "S1004"}


async def test_no_sql_and_bad_inputs_rejected(server) -> None:  # type: ignore[no-untyped-def]
    async with Client(server) as c:
        names = {t.name for t in (await c.call_tool.__self__.list_tools()).tools}
        assert names == {
            "list_tables",
            "get_table_schema",
            "get_dbt_manifest",
            "get_table_stats",
            "run_check",
        }
        assert (await c.call_tool("get_table_schema", {"table": "pg_shadow"})).is_error
        assert (
            await c.call_tool(
                "run_check",
                {"check": "drop_everything", "date_from": "2026-06-01", "date_to": "2026-06-02"},
            )
        ).is_error
        assert (
            await c.call_tool(
                "run_check",
                {"check": "key_drift", "date_from": "2026-06-10", "date_to": "2026-06-01"},
            )
        ).is_error
        assert (
            await c.call_tool("get_table_stats", {"table": "transactions", "date": "yesterday"})
        ).is_error


async def test_manifest_summary(server) -> None:  # type: ignore[no-untyped-def]
    async with Client(server) as c:
        m = (await c.call_tool("get_dbt_manifest", {})).structured_content
    assert m["sources"][0]["name"] == "raw.transactions" and m["sources"][0]["contract_enforced"]
    assert {x["name"] for x in m["models"]} == {"stg_transactions", "dim_outlet", "fct_daily_sales"}
