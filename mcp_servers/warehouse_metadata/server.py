"""warehouse-metadata: schema, dbt manifest, table stats and named checks.

Every query runs in a read-only transaction and every argument is validated
by the tool signature. There is no tool that accepts SQL.
"""

import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import BaseModel, Field
from sqlalchemy import Engine, create_engine, text

from mcp_servers.common import IsoDate

ROOT = Path(__file__).resolve().parents[2]

Table = Literal[
    "transactions",
    "file_loads",
    "outlet_location_map",
    "outlet_alias",
    "submitter_registry",
    "audit_ledger",
]
CONTRACT = [
    "outlet_id",
    "location_id",
    "transaction_id",
    "upc_code",
    "channel_basket_id",
    "qty",
    "amount",
    "event_ts",
]
REFERENCE_TABLES = {"submitter_registry", "outlet_location_map", "outlet_alias"}
DESCRIPTIONS = {
    "transactions": "Raw line items from submitter files, one row per line.",
    "file_loads": "One row per loaded file: header, missing and unexpected columns, landing time.",
    "outlet_location_map": "Canonical outlet to location mapping.",
    "outlet_alias": "Known bad outlet ids and the canonical id they map to.",
    "submitter_registry": "Submitters, their channel and landing SLA.",
    "audit_ledger": "Append-only record of loads, findings and review decisions.",
}


class TableInfo(BaseModel):
    name: str
    row_count: int
    description: str


class TableList(BaseModel):
    tables: list[TableInfo]


class Column(BaseModel):
    name: str
    data_type: str
    nullable: bool = True


class TableSchema(BaseModel):
    table: str
    columns: list[Column]
    contract: list[Column] | None = Field(
        default=None, description="Columns the dbt source contract requires, if one exists"
    )


class ManifestNode(BaseModel):
    name: str
    description: str
    columns: list[Column]
    depends_on: list[str] = []
    contract_enforced: bool = False


class ManifestSummary(BaseModel):
    generated_at: str
    sources: list[ManifestNode]
    models: list[ManifestNode]


class FileStats(BaseModel):
    file_name: str
    submitter_id: str
    rows: int
    produced_at: str
    landed_at: str
    header: list[str]
    missing_columns: list[str]
    unexpected_columns: list[str]
    null_counts: dict[str, int]


class TableStats(BaseModel):
    table: str
    date: str
    row_count: int
    files: list[FileStats] = []
    rows: list[dict[str, Any]] | None = Field(
        default=None, description="Full contents, for the small reference tables only"
    )


class CheckResult(BaseModel):
    check: str
    date_from: str
    date_to: str
    rows_in_window: int
    groups: list[dict[str, Any]]


def _engine() -> Engine:
    url = os.environ.get("DATABASE_URL", "")
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix) :]
    return create_engine(url, pool_pre_ping=True)


def _manifest_path() -> Path:
    return Path(os.environ.get("DBT_MANIFEST", ROOT / "dbt" / "target" / "manifest.json"))


def _day(value: str) -> date:
    return date.fromisoformat(value)


_DEDUP = """
    select t.*,
           split_part(submitter_file_name, '_', 2) || split_part(submitter_file_name, '_', 3)
             as file_ts,
           row_number() over w as rn,
           first_value(submitter_file_name) over w as winning_file,
           first_value(qty) over w as winning_qty,
           first_value(amount) over w as winning_amount
    from transactions t
    where event_ts >= :d0 and event_ts < :d1
    window w as (
      partition by transaction_id, channel_basket_id, upc_code
      order by split_part(submitter_file_name, '_', 2)
               || split_part(submitter_file_name, '_', 3) desc,
               submitter_file_name desc
    )
"""

CHECKS: dict[str, str] = {
    "duplicate_keys": f"""
        with ranked as ({_DEDUP})
        select winning_file, submitter_file_name as superseded_file,
               min(event_ts)::date::text as business_date,
               count(*) as superseded_rows,
               count(*) filter (where qty <> winning_qty or amount <> winning_amount)
                 as changed_rows
        from ranked
        where rn > 1 and channel_basket_id is not null
        group by 1, 2 order by 1, 2
    """,
    "key_drift": f"""
        with ranked as ({_DEDUP}), latest as (select * from ranked where rn = 1)
        select l.location_id, l.outlet_id as reported_outlet_id,
               canon.outlet_id as canonical_outlet_id,
               count(*) as rows,
               count(distinct l.transaction_id) as baskets,
               min(l.event_ts)::date::text as first_seen,
               max(l.event_ts)::date::text as last_seen,
               count(distinct split_part(l.submitter_file_name, '_', 1)) as submitters
        from latest l
        left join outlet_location_map m on m.outlet_id = l.outlet_id
        left join outlet_location_map canon on canon.location_id = l.location_id
        where m.outlet_id is null or m.location_id <> l.location_id
        group by 1, 2, 3 order by rows desc
    """,
}
_WINDOW_ROWS = f"with ranked as ({_DEDUP}) select count(*) from ranked where rn = 1"


def build_server(engine: Engine | None = None, manifest_path: Path | None = None) -> MCPServer:
    server = MCPServer(
        "warehouse-metadata",
        instructions=(
            "Read-only view of the retail warehouse: table list, schemas, the dbt manifest, "
            "per-day table stats and named reconciliation checks. Nothing here writes."
        ),
    )
    state: dict[str, Any] = {"engine": engine}

    def eng() -> Engine:
        if state["engine"] is None:
            state["engine"] = _engine()
        return state["engine"]

    def manifest() -> dict[str, Any]:
        return json.loads((manifest_path or _manifest_path()).read_text())

    def query(sql: str, **params: Any) -> list[dict[str, Any]]:
        with eng().connect().execution_options(postgresql_readonly=True) as conn:
            return [dict(r._mapping) for r in conn.execute(text(sql), params)]

    @server.tool(description="List the warehouse tables with row counts.")
    def list_tables() -> TableList:
        out = []
        for name, desc in DESCRIPTIONS.items():
            n = query(f"select count(*) as n from {name}")[0]["n"]
            out.append(TableInfo(name=name, row_count=n, description=desc))
        return TableList(tables=out)

    @server.tool(description="Physical columns of a table, plus the dbt contract when one exists.")
    def get_table_schema(table: Table) -> TableSchema:
        rows = query(
            "select column_name, data_type, is_nullable = 'YES' as nullable "
            "from information_schema.columns where table_name = :t order by ordinal_position",
            t=table,
        )
        contract = None
        if table == "transactions":
            src = manifest()["sources"]["source.retail_recon.raw.transactions"]
            contract = [
                Column(name=c["name"], data_type=c["data_type"], nullable=False)
                for c in src["columns"].values()
            ]
        return TableSchema(
            table=table,
            columns=[
                Column(name=r["column_name"], data_type=r["data_type"], nullable=r["nullable"])
                for r in rows
            ],
            contract=contract,
        )

    @server.tool(description="Sources and models from the dbt manifest, with their columns.")
    def get_dbt_manifest() -> ManifestSummary:
        m = manifest()

        def node(n: dict[str, Any]) -> ManifestNode:
            return ManifestNode(
                name=(
                    n["name"]
                    if n["resource_type"] == "model"
                    else f"{n['source_name']}.{n['name']}"
                ),
                description=n.get("description", ""),
                columns=[
                    Column(name=c["name"], data_type=c["data_type"]) for c in n["columns"].values()
                ],
                depends_on=n.get("depends_on", {}).get("nodes", []),
                contract_enforced=bool(n.get("config", {}).get("contract", {}).get("enforced")),
            )

        return ManifestSummary(
            generated_at=m["metadata"]["generated_at"],
            sources=[node(n) for n in m["sources"].values()],
            models=[node(n) for n in m["nodes"].values()],
        )

    @server.tool(
        description=(
            "Stats for one table on one business date. For transactions this includes every "
            "file that landed for the date: rows, landing time, header, missing and unexpected "
            "columns against the contract, and null counts per contracted column."
        )
    )
    def get_table_stats(table: Table, date: IsoDate) -> TableStats:
        d = _day(date)
        if table != "transactions":
            n = query(f"select count(*) as n from {table}")[0]["n"]
            rows = None
            if table in REFERENCE_TABLES:
                rows = [
                    {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in r.items()}
                    for r in query(f"select * from {table} order by 1")
                ]
            return TableStats(table=table, date=date, row_count=n, rows=rows)
        nulls = ", ".join(f"count(*) filter (where {c} is null) as null_{c}" for c in CONTRACT)
        rows = query(
            f"select submitter_file_name, count(*) as rows, {nulls} from transactions "
            "where event_ts >= :d0 and event_ts < :d1 group by 1",
            d0=d,
            d1=d + timedelta(days=1),
        )
        loads = {
            r["file_name"]: r
            for r in query(
                "select file_name, submitter_id, produced_at, landed_at, header, "
                "missing_columns, unexpected_columns from file_loads where business_date = :d",
                d=d,
            )
        }
        files = []
        for r in sorted(rows, key=lambda r: r["submitter_file_name"]):
            load = loads.get(r["submitter_file_name"], {})
            files.append(
                FileStats(
                    file_name=r["submitter_file_name"],
                    submitter_id=load.get("submitter_id", r["submitter_file_name"].split("_")[0]),
                    rows=r["rows"],
                    produced_at=load["produced_at"].isoformat() if load else "",
                    landed_at=load["landed_at"].isoformat() if load else "",
                    header=list(load.get("header", [])),
                    missing_columns=list(load.get("missing_columns", [])),
                    unexpected_columns=list(load.get("unexpected_columns", [])),
                    null_counts={c: r[f"null_{c}"] for c in CONTRACT if r[f"null_{c}"]},
                )
            )
        return TableStats(table=table, date=date, row_count=sum(f.rows for f in files), files=files)

    @server.tool(
        description=(
            "Run a named, read-only reconciliation check over a date range. "
            "duplicate_keys: rows superseded by a later file on the dedup key. "
            "key_drift: deduplicated rows whose outlet id is not the one mapped to their location."
        )
    )
    def run_check(
        check: Literal["duplicate_keys", "key_drift"], date_from: IsoDate, date_to: IsoDate
    ) -> CheckResult:
        d0, d1 = _day(date_from), _day(date_to) + timedelta(days=1)
        if d1 <= d0 or (d1 - d0).days > 366:
            raise ValueError("date range must be positive and at most a year")
        groups = query(CHECKS[check], d0=d0, d1=d1)
        total = query(_WINDOW_ROWS, d0=d0, d1=d1)[0]["count"]
        return CheckResult(
            check=check, date_from=date_from, date_to=date_to, rows_in_window=total, groups=groups
        )

    return server
