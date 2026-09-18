"""Retail transaction reconciliation: every business rule for this domain.

The dedup key, the key-drift pair, schema-drift tolerance, the volume window
and thresholds, the severity rubric and the write-up wording all live here.
"""

import asyncio
import re
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any

from app.domain.protocol import (
    Evidence,
    Finding,
    FindingAnalysis,
    Scope,
    Severity,
    SpecialistSpec,
    ToolBox,
)
from app.retrieval.types import RetrievedChunk

WAREHOUSE = "warehouse-metadata"
ORCHESTRATION = "orchestration-metadata"
DAG_ID = "retail_txn_daily"

DEDUP_KEY = ("transaction_id", "channel_basket_id", "upc_code")
KEY_DRIFT_PAIR = ("outlet_id", "location_id")
KEY_DRIFT_S2_RATE = 0.02
VOLUME_WINDOW_DAYS = 7
VOLUME_DROP = 0.25
VOLUME_DROP_S1 = 0.50
VOLUME_SPIKE = 0.60
MIN_HISTORY_DAYS = 3

_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def _file_ts(name: str) -> str:
    """``S1002_20260612_1120_ECOMM.txt`` -> ``20260612_1120``; the latest file wins."""
    parts = name.split("_")
    return f"{parts[1]}_{parts[2]}" if len(parts) >= 3 else name


def _similar(a: str, b: str) -> float:
    ta, tb = set(a.lower().split("_")), set(b.lower().split("_"))
    return len(ta & tb) / max(len(ta | tb), 1)


def _minutes(a: str, b: str) -> int:
    return int((datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds() // 60)


class RetailReconAdapter:
    name = "retail_recon"
    title = "Retail transaction reconciliation"
    scan_keywords = [
        "scan",
        "check the pipeline",
        "anything wrong",
        "any issues",
        "what's wrong",
        "what is wrong",
        "health",
        "problems",
        "incidents",
        "everything ok",
        "investigate",
    ]
    specialists = [
        SpecialistSpec(
            role="reconciliation",
            title="Reconciliation",
            description=(
                "Applies the dedup key and the latest-file-wins rule, and flags outlet / "
                "location key drift."
            ),
            finding_types=["duplicate_submission", "key_drift"],
            keywords=[
                "duplicate",
                "dedup",
                "resend",
                "resent",
                "twice",
                "double",
                "superseded",
                "drift",
                "outlet",
                "location",
                "two ids",
                "store",
                "reconcil",
                "key",
            ],
        ),
        SpecialistSpec(
            role="data_quality",
            title="Data-Quality",
            description=(
                "Diffs each batch against the dbt contract and checks volume and timing "
                "against DAG history."
            ),
            finding_types=["schema_drift", "volume_anomaly"],
            keywords=[
                "schema",
                "column",
                "renamed",
                "dropped",
                "contract",
                "header",
                "volume",
                "light",
                "rows",
                "count",
                "late",
                "sla",
                "dag",
                "task",
                "failed",
                "sensor",
                "missing",
                "truncated",
                "anomal",
            ],
        ),
    ]

    # -- scope ---------------------------------------------------------------

    async def resolve_scope(self, question: str | None, tools: ToolBox) -> Scope:
        runs = await tools.call(ORCHESTRATION, "list_dag_runs", {"dag_id": DAG_ID})
        dates = sorted(r["business_date"] for r in runs["runs"])
        last = date.fromisoformat(dates[-1]) if dates else date.today()
        first = date.fromisoformat(dates[0]) if dates else last - timedelta(days=20)
        mentioned = sorted(_DATE.findall(question or ""))
        if mentioned:
            d0 = date.fromisoformat(mentioned[0])
            d1 = date.fromisoformat(mentioned[-1])
            # keep a week of history before the day asked about, for trailing averages
            return Scope(date_from=max(first, d0 - timedelta(days=VOLUME_WINDOW_DAYS)), date_to=d1)
        return Scope(date_from=first, date_to=last)

    # -- checks --------------------------------------------------------------

    async def run_checks(self, role: str, tools: ToolBox, scope: Scope) -> list[Finding]:
        if role == "reconciliation":
            dups, drift = await asyncio.gather(
                self._duplicates(tools, scope), self._key_drift(tools, scope)
            )
            findings = dups + drift
        elif role == "data_quality":
            findings = await self._data_quality(tools, scope)
        else:
            raise ValueError(f"unknown specialist {role}")
        for f in findings:
            f.severity = self.severity(f)
        return findings

    async def _duplicates(self, tools: ToolBox, scope: Scope) -> list[Finding]:
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

    async def _key_drift(self, tools: ToolBox, scope: Scope) -> list[Finding]:
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

    async def _data_quality(self, tools: ToolBox, scope: Scope) -> list[Finding]:
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
        findings = self._schema_drift(per_day, contract, failed)
        findings += self._volume(per_day, registry, timings)
        return findings

    def _schema_drift(
        self, per_day: list[dict[str, Any]], contract: list[str], failed: dict[str, Any]
    ) -> list[Finding]:
        out = []
        for day in per_day:
            for f in day["files"]:
                missing = [c for c in contract if c not in f["header"]]
                unexpected = [c for c in f["header"] if c not in contract]
                if not missing and not unexpected:
                    continue
                renames = [(m, u) for m in missing for u in unexpected if _similar(m, u) >= 0.25]
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

    def _volume(
        self, per_day: list[dict[str, Any]], registry: dict[str, Any], timings: dict[str, Any]
    ) -> list[Finding]:
        sla = {r["submitter_id"]: r["sla_hhmm"] for r in registry.get("rows") or []}
        sensor = next(
            (t for t in timings["tasks"] if t["task_id"] == "wait_for_submitter_files"), None
        )
        sensor_by_day = {
            h["business_date"]: h["duration_s"] for h in (sensor or {}).get("history", [])
        }
        # latest file per submitter per day: a resend replaces, it doesn't add
        series: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for day in per_day:
            latest: dict[str, dict[str, Any]] = {}
            for f in day["files"]:
                cur = latest.get(f["submitter_id"])
                if cur is None or _file_ts(f["file_name"]) > _file_ts(cur["file_name"]):
                    latest[f["submitter_id"]] = f
            for sid, f in latest.items():
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
                    late_by = _minutes(f["landed_at"], due.isoformat())
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

    # -- dashboard -------------------------------------------------------------

    async def overview(self, tools: ToolBox) -> dict[str, Any]:
        """Volume for the latest business date against its trailing week, and the last run."""
        runs = (await tools.call(ORCHESTRATION, "list_dag_runs", {"dag_id": DAG_ID}))["runs"]
        if not runs:
            return {"as_of": None, "volume": None, "last_run": None}
        runs.sort(key=lambda r: r["business_date"])
        last = runs[-1]
        as_of = date.fromisoformat(last["business_date"])
        days = [as_of - timedelta(days=i) for i in range(13, -1, -1)]
        stats = await asyncio.gather(
            *(
                tools.call(WAREHOUSE, "get_table_stats", {"table": "transactions", "date": str(d)})
                for d in days
            )
        )
        series = []
        for d, day in zip(days, stats, strict=True):
            latest: dict[str, dict[str, Any]] = {}
            for f in day["files"]:
                cur = latest.get(f["submitter_id"])
                if cur is None or _file_ts(f["file_name"]) > _file_ts(cur["file_name"]):
                    latest[f["submitter_id"]] = f
            series.append(
                {
                    "date": str(d),
                    "rows": sum(f["rows"] for f in latest.values()),
                    "by_submitter": {k: v["rows"] for k, v in sorted(latest.items())},
                }
            )
        trailing = [s["rows"] for s in series[-1 - VOLUME_WINDOW_DAYS : -1] if s["rows"]]
        avg = mean(trailing) if trailing else 0.0
        today = series[-1]["rows"]
        return {
            "as_of": str(as_of),
            "volume": {
                "rows": today,
                "trailing_avg_7d": round(avg, 1),
                "pct_change": round(today / avg - 1, 3) if avg else None,
                "series": series,
            },
            "last_run": {
                "business_date": last["business_date"],
                "state": last["state"],
                "duration_s": last["duration_s"],
                "failed_tasks": last["failed_tasks"],
                "runs_failed_14d": sum(1 for r in runs[-14:] if r["state"] == "failed"),
            },
        }

    # -- rubric and wording ----------------------------------------------------

    def severity(self, finding: Finding) -> Severity:
        m = finding.metrics
        if finding.finding_type == "key_drift":
            return "S2" if (finding.affected_rate or 0) > KEY_DRIFT_S2_RATE else "S3"
        if finding.finding_type == "duplicate_submission":
            return "S2" if m.get("landed_after_dag_run") else "S3"
        if finding.finding_type == "schema_drift":
            if m.get("change") == "add":
                return "S4"
            return "S1" if m.get("dedup_key_affected") else "S2"
        if finding.finding_type == "volume_anomaly":
            change = m.get("pct_change", 0)
            if change <= -VOLUME_DROP_S1:
                return "S1"
            return "S2" if change <= -VOLUME_DROP else "S3"
        return "S3"

    def problem_statement(self, finding: Finding) -> str:
        m = finding.metrics
        if finding.finding_type == "key_drift":
            return (
                f"Location {m['location_id']} is reporting sales under two outlet ids: its "
                f"canonical {m['canonical_outlet_id']} and {m['reported_outlet_id']}, which "
                f"outlet_location_map does not map to it. {m['rows']} of {m['rows_in_window']} "
                f"deduplicated rows ({finding.affected_rate:.1%}) between {m['first_seen']} and "
                f"{m['last_seen']} are affected, so store-level numbers for this location "
                "are split."
            )
        if finding.finding_type == "duplicate_submission":
            when = "after" if m["landed_after_dag_run"] else "before"
            return (
                f"{m['submitter_id']} resent its {m['business_date']} file. "
                f"{m['winning_file']} repeats {m['duplicate_keys']} dedup keys from "
                f"{m['superseded_file']}, and {m['changed_rows']} of them carry a different qty or "
                f"amount. The resend landed {when} that night's DAG run, so the superseded rows "
                f"{'reached' if m['landed_after_dag_run'] else 'did not reach'} fct_daily_sales."
            )
        if finding.finding_type == "schema_drift":
            return (
                f"{m['file']} ({m['business_date']}) does not match the raw.transactions contract: "
                f"missing {m['missing_columns']}, unexpected {m['unexpected_columns']}. "
                f"{finding.affected_records} rows landed with the missing column null"
                + (
                    "; that column is part of the dedup key, so dedup cannot run for this batch."
                    if m["dedup_key_affected"]
                    else "."
                )
            )
        if finding.finding_type == "volume_anomaly":
            late = m.get("minutes_after_sla")
            return (
                f"{m['submitter_id']}'s {m['business_date']} file {m['file']} has "
                f"{m['rows']} rows, "
                f"{abs(m['pct_change']):.0%} {'below' if m['pct_change'] < 0 else 'above'} its "
                f"trailing 7-day average of {m['trailing_avg_7d']}"
                + (
                    f", and it landed {late} minutes after the submitter SLA."
                    if late and late > 0
                    else "."
                )
            )
        return finding.title

    def retrieval_query(self, finding: Finding) -> str:
        m = finding.metrics
        return {
            "key_drift": "location reporting under two outlet ids key drift fix outlet_alias",
            "duplicate_submission": "resend duplicate submission latest file wins dedupe reprocess",
            "schema_drift": (
                f"renamed column {' '.join(m.get('missing_columns', []))} "
                f"{' '.join(m.get('unexpected_columns', []))} ContractViolation validate_schema"
            ),
            "volume_anomaly": "volume drop below trailing average late truncated file",
        }.get(finding.finding_type, finding.title)

    def fallback_analysis(self, finding: Finding, sources: list[RetrievedChunk]) -> FindingAnalysis:
        m = finding.metrics
        precedent = next((s.title.split(":")[0] for s in sources if s.doc_type == "incident"), None)
        like = f" This matches the pattern in {precedent}." if precedent else ""
        if finding.finding_type == "key_drift":
            return FindingAnalysis(
                root_cause_hypothesis=(
                    f"Whole baskets ({m['baskets']}) from {m['submitters']} submitter(s) carry "
                    f"{m['reported_outlet_id']}, so the id is set at the register or export "
                    f"profile rather than corrupted row by row; {m['reported_outlet_id']} looks "
                    f"like a transposition of {m['canonical_outlet_id']}.{like}"
                ),
                recommended_fix=[
                    "Confirm the correct outlet id with the submitter before changing anything.",
                    f"Add {m['reported_outlet_id']} -> {m['canonical_outlet_id']} to outlet_alias "
                    f"for {m['first_seen']} to {m['last_seen']}; never edit raw rows.",
                    "Rebuild stg_transactions and fct_daily_sales for the affected dates.",
                    "Ask the submitter to fix the export profile at source and record the ticket.",
                ],
                confidence=0.6,
                open_questions=[
                    "Which registers or export profiles carry the wrong id?",
                    f"Did the drift start on {m['first_seen']} or earlier than the scan window?",
                ],
            )
        if finding.finding_type == "duplicate_submission":
            corrected = m["changed_rows"] > 0
            return FindingAnalysis(
                root_cause_hypothesis=(
                    (
                        f"A deliberate correction: {m['changed_rows']} rows changed qty or amount, "
                        "so the later file is the one to trust. "
                        if corrected
                        else "An accidental re-export: no values changed. "
                    )
                    + (
                        "It landed after dedupe_transactions had run, so nothing removed the older "
                        "copies before publish."
                        if m["landed_after_dag_run"]
                        else "Dedupe ran after it landed, so published numbers are correct."
                    )
                    + like
                ),
                recommended_fix=[
                    f"Reprocess {m['business_date']} with reprocess=true so dedupe_transactions "
                    "runs again and the latest file wins.",
                    "Check publish_metrics against the resend's trailer count.",
                    "Tell finance how many rows changed value, not just how many were duplicated.",
                ],
                confidence=0.75 if corrected else 0.6,
                open_questions=[f"Why did {m['submitter_id']} resend: correction or re-run?"],
            )
        if finding.finding_type == "schema_drift":
            rename = m["renames"][0] if m["renames"] else None
            return FindingAnalysis(
                root_cause_hypothesis=(
                    (
                        f"The submitter's export renamed {rename[0]} to {rename[1]}: one "
                        "contracted column is missing and one similarly named column appeared "
                        "in the same batch. "
                        if rename
                        else "The export changed its header against the contract. "
                    )
                    + "The loader maps by name, so the rows landed with the column null."
                    + like
                ),
                recommended_fix=[
                    "Do not change the contract to match the file.",
                    f"Ask {m['submitter_id']} to resend {m['business_date']} with the "
                    "contracted header.",
                    "Reprocess the day once the resend lands; latest-file-wins supersedes the "
                    "null-key rows.",
                ],
                confidence=0.8 if rename else 0.6,
                open_questions=["Did the submitter ship a new export library or config?"],
            )
        if finding.finding_type == "volume_anomaly":
            late = (m.get("minutes_after_sla") or 0) > 0
            return FindingAnalysis(
                root_cause_hypothesis=(
                    (
                        "A late and light file together is the signature of a truncated upstream "
                        "export: the transfer shipped whatever was there once its retry window "
                        "ran out."
                        if late and m["pct_change"] < 0
                        else "Volume moved outside its normal band without a timing signal."
                    )
                    + like
                ),
                recommended_fix=[
                    "Check whether the drop is spread across all outlets (truncation) or a few "
                    "(stores offline).",
                    "Compare the loaded row count with the file trailer.",
                    f"If truncated, request a full resend from {m['submitter_id']} and "
                    f"reprocess {m['business_date']}.",
                ],
                confidence=0.65 if late else 0.45,
                open_questions=[
                    "Was it a known low day (holiday, planned closures)?",
                    "Is the drop spread evenly across outlets?",
                ],
            )
        return FindingAnalysis(
            root_cause_hypothesis="No template for this finding type; needs a human look.",
            recommended_fix=["Review the evidence attached to the finding."],
            confidence=0.3,
        )
