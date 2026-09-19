"""The checks behind the two retail specialists.

Each check asks the MCP tool servers for facts and returns ``Finding`` objects
with record counts and evidence. Nothing here calls a model: the numbers in a
report are measured, never generated.
"""

import asyncio
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from app.domain.protocol import Evidence, Finding, Scope, ToolBox
from app.domain.retail_recon.rules import (
    DAG_ID,
    DEDUP_KEY,
    MIN_HISTORY_DAYS,
    ORCHESTRATION,
    VOLUME_DROP,
    VOLUME_SPIKE,
    VOLUME_WINDOW_DAYS,
    WAREHOUSE,
    latest_file_per_submitter,
    minutes_between,
    name_similarity,
)

# -- Reconciliation specialist ---------------------------------------------------


async def duplicate_submissions(tools: ToolBox, scope: Scope) -> list[Finding]:
    res = await tools.call(
        WAREHOUSE,
        "run_check",
        {
            "check": "duplicate_keys",
            "date_from": str(scope.date_from),
            "date_to": str(scope.date_to),
        },
    )
    if not res["groups"]:
        return []
    runs = await tools.call(ORCHESTRATION, "list_dag_runs", {"dag_id": DAG_ID})
    run_end = {r["business_date"]: r["end"] for r in runs["runs"]}
    out = []
    for g in res["groups"]:
        bdate = g["business_date"]
        stats = await tools.call(
            WAREHOUSE, "get_table_stats", {"table": "transactions", "date": bdate}
        )
        landed = {f["file_name"]: f["landed_at"] for f in stats["files"]}
        winner_landed = landed.get(g["winning_file"], "")
        end = run_end.get(bdate)
        after_dag = bool(end and winner_landed and winner_landed > end.replace("Z", "+00:00"))
        out.append(
            Finding(
                finding_type="duplicate_submission",
                specialist="reconciliation",
                subject=g["winning_file"],
                title=f"Resent file {g['winning_file']} supersedes {g['superseded_rows']} rows",
                affected_records=g["superseded_rows"],
                metrics={
                    "business_date": bdate,
                    "submitter_id": g["winning_file"].split("_")[0],
                    "winning_file": g["winning_file"],
                    "superseded_file": g["superseded_file"],
                    "duplicate_keys": g["superseded_rows"],
                    "superseded_rows": g["superseded_rows"],
                    "changed_rows": g["changed_rows"],
                    "winner_landed_at": winner_landed,
                    "dag_run_end": end,
                    "landed_after_dag_run": after_dag,
                },
                evidence=[
                    Evidence(
                        source=f"mcp:{WAREHOUSE}/run_check",
                        summary=(
                            f"{g['superseded_rows']} keys in {g['superseded_file']} are "
                            f"superseded by {g['winning_file']}; {g['changed_rows']} changed "
                            "qty or amount"
                        ),
                        data=g,
                    ),
                    Evidence(
                        source=f"mcp:{ORCHESTRATION}/list_dag_runs",
                        summary=(
                            f"{DAG_ID} for {bdate} finished at {end}; the resend landed "
                            f"{'after' if after_dag else 'before'} it"
                        ),
                    ),
                ],
            )
        )
    return out


async def key_drift(tools: ToolBox, scope: Scope) -> list[Finding]:
    res = await tools.call(
        WAREHOUSE,
        "run_check",
        {
            "check": "key_drift",
            "date_from": str(scope.date_from),
            "date_to": str(scope.date_to),
        },
    )
    total = res["rows_in_window"] or 1
    out = []
    for g in res["groups"]:
        rate = g["rows"] / total
        out.append(
            Finding(
                finding_type="key_drift",
                specialist="reconciliation",
                subject=g["location_id"],
                title=(
                    f"{g['location_id']} also reporting as {g['reported_outlet_id']} "
                    f"({rate:.1%} of rows)"
                ),
                affected_records=g["rows"],
                affected_rate=round(rate, 4),
                metrics={
                    "location_id": g["location_id"],
                    "canonical_outlet_id": g["canonical_outlet_id"],
                    "reported_outlet_id": g["reported_outlet_id"],
                    "rows": g["rows"],
                    "baskets": g["baskets"],
                    "rows_in_window": res["rows_in_window"],
                    "first_seen": g["first_seen"],
                    "last_seen": g["last_seen"],
                    "submitters": g["submitters"],
                },
                evidence=[
                    Evidence(
                        source=f"mcp:{WAREHOUSE}/run_check",
                        summary=(
                            f"{g['rows']} deduplicated rows ({g['baskets']} baskets) at "
                            f"{g['location_id']} carry {g['reported_outlet_id']}, which "
                            f"outlet_location_map does not map there; canonical is "
                            f"{g['canonical_outlet_id']}"
                        ),
                        data=g,
                    )
                ],
            )
        )
    return out


# -- Data-Quality specialist -------------------------------------------------------


async def data_quality(tools: ToolBox, scope: Scope) -> list[Finding]:
    days = [
        scope.date_from + timedelta(days=i)
        for i in range((scope.date_to - scope.date_from).days + 1)
    ]
    # every per-day lookup is independent, so fetch them together
    manifest, registry, failed, timings, *per_day = await asyncio.gather(
        tools.call(WAREHOUSE, "get_dbt_manifest", {}),
        tools.call(
            WAREHOUSE,
            "get_table_stats",
            {"table": "submitter_registry", "date": str(scope.date_to)},
        ),
        tools.call(ORCHESTRATION, "get_failed_tasks", {"since": str(scope.date_from)}),
        tools.call(ORCHESTRATION, "get_timing_history", {"dag_id": DAG_ID}),
        *(
            tools.call(WAREHOUSE, "get_table_stats", {"table": "transactions", "date": str(d)})
            for d in days
        ),
    )
    contract = next(
        [c["name"] for c in s["columns"] if c["name"] != "submitter_file_name"]
        for s in manifest["sources"]
        if s["name"] == "raw.transactions"
    )
    findings = schema_drift(per_day, contract, failed)
    findings += volume_anomalies(per_day, registry, timings)
    return findings


def schema_drift(
    per_day: list[dict[str, Any]], contract: list[str], failed: dict[str, Any]
) -> list[Finding]:
    out = []
    for day in per_day:
        for f in day["files"]:
            missing = [c for c in contract if c not in f["header"]]
            unexpected = [c for c in f["header"] if c not in contract]
            if not missing and not unexpected:
                continue
            renames = [(m, u) for m in missing for u in unexpected if name_similarity(m, u) >= 0.25]
            change = "rename" if renames else ("drop" if missing else "add")
            task = next(
                (t for t in failed["failures"] if f["file_name"] in t["first_error_line"]), None
            )
            evidence = [
                Evidence(
                    source=f"mcp:{WAREHOUSE}/get_table_stats",
                    summary=(
                        f"{f['file_name']} header is missing {missing} and has unexpected "
                        f"{unexpected}; "
                        f"{f['null_counts'].get(missing[0], 0) if missing else 0} "
                        "rows landed with the missing column null"
                    ),
                    data={"header": f["header"], "null_counts": f["null_counts"]},
                ),
                Evidence(
                    source=f"mcp:{WAREHOUSE}/get_dbt_manifest",
                    summary="raw.transactions contract: " + ", ".join(contract),
                ),
            ]
            if task:
                evidence.append(
                    Evidence(
                        source=f"mcp:{ORCHESTRATION}/get_failed_tasks",
                        summary=(
                            f"{task['task_id']} failed on {task['business_date']}: "
                            f"{task['first_error_line']}"
                        ),
                        data=task,
                    )
                )
            out.append(
                Finding(
                    finding_type="schema_drift",
                    specialist="data_quality",
                    subject=f["file_name"],
                    title=(
                        f"{f['file_name']} renamed {renames[0][0]} to {renames[0][1]}"
                        if renames
                        else f"{f['file_name']} does not match the contract"
                    ),
                    affected_records=f["rows"],
                    metrics={
                        "business_date": day["date"],
                        "file": f["file_name"],
                        "submitter_id": f["submitter_id"],
                        "missing_columns": missing,
                        "unexpected_columns": unexpected,
                        "change": change,
                        "renames": [list(r) for r in renames],
                        "dedup_key_affected": any(c in DEDUP_KEY for c in missing),
                        "failed_task": task["task_id"] if task else None,
                    },
                    evidence=evidence,
                )
            )
    return out


def volume_anomalies(
    per_day: list[dict[str, Any]], registry: dict[str, Any], timings: dict[str, Any]
) -> list[Finding]:
    sla = {r["submitter_id"]: r["sla_hhmm"] for r in registry.get("rows") or []}
    sensor = next((t for t in timings["tasks"] if t["task_id"] == "wait_for_submitter_files"), None)
    sensor_by_day = {h["business_date"]: h["duration_s"] for h in (sensor or {}).get("history", [])}
    # a resend replaces the earlier file, it doesn't add to it
    series: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for day in per_day:
        for sid, f in latest_file_per_submitter(day["files"]).items():
            series.setdefault(sid, []).append((day["date"], f))
    out = []
    for sid, days in sorted(series.items()):
        for i, (d, f) in enumerate(days):
            history = [x["rows"] for _, x in days[max(0, i - VOLUME_WINDOW_DAYS) : i]]
            if len(history) < MIN_HISTORY_DAYS:
                continue
            trailing = mean(history)
            change = f["rows"] / trailing - 1
            if -change < VOLUME_DROP and change < VOLUME_SPIKE:
                continue
            late_by = None
            if sid in sla and f["landed_at"]:
                hh, mm = sla[sid].split(":")
                due = datetime.fromisoformat(f["landed_at"]).replace(
                    hour=int(hh), minute=int(mm), second=0
                )
                late_by = minutes_between(f["landed_at"], due.isoformat())
            sensor_s = sensor_by_day.get(d)
            out.append(
                Finding(
                    finding_type="volume_anomaly",
                    specialist="data_quality",
                    subject=f"{sid} {d}",
                    title=(
                        f"{sid} {d}: {f['rows']} rows, {abs(change):.0%} "
                        f"{'below' if change < 0 else 'above'} its 7-day average"
                    ),
                    affected_records=round(trailing - f["rows"]) if change < 0 else f["rows"],
                    affected_rate=round(change, 3),
                    metrics={
                        "business_date": d,
                        "submitter_id": sid,
                        "file": f["file_name"],
                        "rows": f["rows"],
                        "trailing_avg_7d": round(trailing, 1),
                        "pct_change": round(change, 3),
                        "landed_at": f["landed_at"],
                        "minutes_after_sla": late_by,
                        "sensor_duration_s": sensor_s,
                        "sensor_median_s": sensor["median_s"] if sensor else None,
                    },
                    evidence=[
                        Evidence(
                            source=f"mcp:{WAREHOUSE}/get_table_stats",
                            summary=(
                                f"{f['file_name']} has {f['rows']} rows against a trailing "
                                f"average of {trailing:.1f}"
                            ),
                        ),
                        Evidence(
                            source=f"mcp:{ORCHESTRATION}/get_timing_history",
                            summary=(
                                f"wait_for_submitter_files took {sensor_s}s on {d} "
                                f"(median {sensor['median_s'] if sensor else '?'}s); "
                                "file landed "
                                f"{late_by} minutes after the {sla.get(sid, '?')} SLA"
                            ),
                        ),
                    ],
                )
            )
    return out
