"""Seeded generator for the synthetic retail transaction pipeline.

Produces what a real landing zone would hold: one pipe-delimited file per
submitter per business day, plus the orchestrator's run history. Four problems
are planted on purpose (key drift, a same-day resend, a renamed column, a light
and late file) and their exact sizes are returned alongside the data so tests
can assert on counts rather than on "something was found".

Everything is driven by one ``random.Random(seed)`` and iterated in a fixed
order, so the same config always produces byte-identical output.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

CONTRACT_COLUMNS = [
    "outlet_id",
    "location_id",
    "transaction_id",
    "upc_code",
    "channel_basket_id",
    "qty",
    "amount",
    "event_ts",
]
DEDUP_KEY = ("transaction_id", "channel_basket_id", "upc_code")

KEY_DRIFT = "key_drift"
DUPLICATES = "duplicate_submission"
SCHEMA_DRIFT = "schema_drift"
VOLUME = "volume_anomaly"
ALL_ANOMALIES = frozenset({KEY_DRIFT, DUPLICATES, SCHEMA_DRIFT, VOLUME})

DAG_ID = "retail_txn_daily"
DAG_TASKS = [
    "wait_for_submitter_files",
    "load_raw_transactions",
    "validate_schema",
    "dedupe_transactions",
    "build_stg_transactions",
    "build_fct_daily_sales",
    "publish_metrics",
]
# typical durations in seconds (low, high) for each task after the sensor
TASK_DURATIONS = {
    "load_raw_transactions": (180, 360),
    "validate_schema": (15, 50),
    "dedupe_transactions": (120, 240),
    "build_stg_transactions": (240, 480),
    "build_fct_daily_sales": (180, 360),
    "publish_metrics": (10, 40),
}
DAG_START = timedelta(hours=5, minutes=15)


@dataclass(frozen=True)
class Submitter:
    submitter_id: str
    name: str
    channel: str
    share: float
    sla_hhmm: str
    produce_window: tuple[int, int]  # minutes after midnight, morning after the business date
    contact: str


SUBMITTERS = (
    Submitter("S1001", "POSFEED", "store", 0.45, "04:00", (125, 160), "pos-integrations"),
    Submitter("S1002", "ECOMM", "web", 0.22, "03:30", (165, 190), "web-platform"),
    Submitter("S1003", "MOBILE", "app", 0.20, "03:30", (135, 165), "mobile-platform"),
    Submitter("S1004", "KIOSK", "kiosk", 0.13, "05:00", (215, 275), "store-systems"),
)


@dataclass(frozen=True)
class GeneratorConfig:
    seed: int = 42
    start: date = date(2026, 6, 1)
    days: int = 21
    rows_per_day: int = 400
    n_locations: int = 40
    anomalies: frozenset[str] = ALL_ANOMALIES

    drift_location: str = "LOC-0517"
    drift_outlet: str = "OUT-1071"
    drift_location_weight: float = 2.1
    drift_share: float = 0.6

    duplicate_day: int = 11
    duplicate_submitter: str = "S1002"
    duplicate_resend_hhmm: str = "1120"
    duplicate_changed_share: float = 0.04

    schema_drift_day: int = 15
    schema_drift_submitter: str = "S1003"
    schema_drift_rename: tuple[str, str] = ("channel_basket_id", "basket_ref")

    volume_day: int = 17
    volume_submitter: str = "S1001"
    volume_factor: float = 0.60
    volume_late_hhmm: str = "0638"

    def business_date(self, day_index: int) -> date:
        return self.start + timedelta(days=day_index)


@dataclass
class LandingFile:
    name: str
    submitter_id: str
    business_date: date
    produced_at: datetime
    landed_at: datetime
    header: list[str]
    rows: list[list[str]]

    def render(self) -> str:
        lines = ["|".join(self.header)]
        lines += ["|".join(r) for r in self.rows]
        lines.append(f"TRAILER|{len(self.rows)}")
        return "\n".join(lines) + "\n"


@dataclass
class SyntheticPipeline:
    config: GeneratorConfig
    files: list[LandingFile]
    dag_runs: list[dict[str, Any]]
    expected: dict[str, Any]
    outlets: list[tuple[str, str]] = field(default_factory=list)  # (outlet_id, location_id)

    @property
    def total_rows(self) -> int:
        return sum(len(f.rows) for f in self.files)


def file_name(submitter: Submitter, business_date: date, hhmm: str) -> str:
    return f"{submitter.submitter_id}_{business_date:%Y%m%d}_{hhmm}_{submitter.name}.txt"


def parse_file_name(name: str) -> tuple[str, date, str, str]:
    """``S1001_20260601_0215_POSFEED.txt`` -> (submitter_id, business_date, hhmm, name)."""
    stem = name.removesuffix(".txt")
    submitter_id, ymd, hhmm, short = stem.split("_", 3)
    return submitter_id, datetime.strptime(ymd, "%Y%m%d").date(), hhmm, short


def _upc(rng: random.Random) -> str:
    digits = [rng.randrange(10) for _ in range(11)]
    odd = sum(digits[0::2])
    even = sum(digits[1::2])
    check = (10 - (odd * 3 + even) % 10) % 10
    return "".join(map(str, digits)) + str(check)


def _iso(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


class _Generator:
    def __init__(self, cfg: GeneratorConfig) -> None:
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.locations = [f"LOC-{501 + i:04d}" for i in range(cfg.n_locations)]
        self.outlets = [(f"OUT-{1001 + i}", loc) for i, loc in enumerate(self.locations)]
        self.canonical = {loc: out for out, loc in self.outlets}
        self.weights = [
            cfg.drift_location_weight if loc == cfg.drift_location else 1.0
            for loc in self.locations
        ]
        self.catalog = [
            (_upc(self.rng), round(self.rng.uniform(0.99, 49.99), 2)) for _ in range(300)
        ]
        self.txn_counter = {s.submitter_id: 0 for s in SUBMITTERS}
        self.drifted_rows = 0

    def _rows_for(self, submitter: Submitter, business_date: date, target: int) -> list[list[str]]:
        rng, cfg = self.rng, self.cfg
        rows: list[tuple[str, list[str]]] = []
        drift_on = KEY_DRIFT in cfg.anomalies
        while len(rows) < target:
            self.txn_counter[submitter.submitter_id] += 1
            txn = f"TXN-{submitter.submitter_id[-1]}{self.txn_counter[submitter.submitter_id]:07d}"
            basket = f"BSK-{rng.getrandbits(32):08X}"
            location = rng.choices(self.locations, weights=self.weights)[0]
            # drift happens per register, so a whole basket goes out under one id
            outlet = self.canonical[location]
            if drift_on and location == cfg.drift_location and rng.random() < cfg.drift_share:
                outlet = cfg.drift_outlet
            ts = datetime(
                business_date.year, business_date.month, business_date.day, tzinfo=UTC
            ) + timedelta(seconds=rng.randrange(6 * 3600, 23 * 3600))
            n_items = rng.choices([1, 2, 3, 4], weights=[50, 30, 15, 5])[0]
            n_items = min(n_items, target - len(rows))
            for upc, price in rng.sample(self.catalog, n_items):
                qty = rng.choices([1, 2, 3], weights=[75, 18, 7])[0]
                if rng.random() < 0.02:
                    qty = -qty
                if outlet == cfg.drift_outlet:
                    self.drifted_rows += 1
                rows.append(
                    (
                        _iso(ts),
                        [
                            outlet,
                            location,
                            txn,
                            upc,
                            basket,
                            str(qty),
                            f"{price * qty:.2f}",
                            _iso(ts),
                        ],
                    )
                )
        rows.sort(key=lambda r: (r[0], r[1][2], r[1][3]))
        return [r for _, r in rows]

    def _produce_time(self, submitter: Submitter, business_date: date) -> tuple[str, datetime]:
        lo, hi = submitter.produce_window
        minutes = self.rng.randrange(lo, hi)
        hhmm = f"{minutes // 60:02d}{minutes % 60:02d}"
        return hhmm, self._at(business_date, hhmm)

    @staticmethod
    def _at(business_date: date, hhmm: str) -> datetime:
        morning = business_date + timedelta(days=1)
        return datetime(
            morning.year, morning.month, morning.day, int(hhmm[:2]), int(hhmm[2:]), tzinfo=UTC
        )

    def run(self) -> SyntheticPipeline:
        cfg, rng = self.cfg, self.rng
        files: list[LandingFile] = []
        counts: dict[str, list[int]] = {s.submitter_id: [] for s in SUBMITTERS}
        expected: dict[str, Any] = {}
        resend_names: set[str] = set()

        for day in range(cfg.days):
            bdate = cfg.business_date(day)
            for sub in SUBMITTERS:
                target = round(cfg.rows_per_day * sub.share * (1 + rng.uniform(-0.05, 0.05)))
                hhmm, produced = self._produce_time(sub, bdate)
                is_volume_day = (
                    VOLUME in cfg.anomalies
                    and day == cfg.volume_day
                    and sub.submitter_id == cfg.volume_submitter
                )
                if is_volume_day:
                    history = counts[sub.submitter_id][-7:]
                    trailing = sum(history) / len(history)
                    target = round(trailing * cfg.volume_factor)
                    hhmm = cfg.volume_late_hhmm
                    produced = self._at(bdate, hhmm)
                rows = self._rows_for(sub, bdate, target)
                counts[sub.submitter_id].append(len(rows))
                header = list(CONTRACT_COLUMNS)
                if (
                    SCHEMA_DRIFT in cfg.anomalies
                    and day == cfg.schema_drift_day
                    and sub.submitter_id == cfg.schema_drift_submitter
                ):
                    old, new = cfg.schema_drift_rename
                    header[header.index(old)] = new
                landed = produced + timedelta(minutes=rng.randrange(1, 5))
                f = LandingFile(
                    name=file_name(sub, bdate, hhmm),
                    submitter_id=sub.submitter_id,
                    business_date=bdate,
                    produced_at=produced,
                    landed_at=landed,
                    header=header,
                    rows=rows,
                )
                files.append(f)
                if is_volume_day:
                    sla = self._at(bdate, sub.sla_hhmm.replace(":", ""))
                    expected[VOLUME] = {
                        "business_date": bdate.isoformat(),
                        "submitter_id": sub.submitter_id,
                        "file": f.name,
                        "rows": len(rows),
                        "trailing_avg_7d": round(trailing, 1),
                        "pct_below_trailing": round(1 - len(rows) / trailing, 3),
                        "landed_at": _iso(landed),
                        "minutes_after_sla": int((landed - sla).total_seconds() // 60),
                        "expected_agent": "data_quality",
                        "expected_severity": "S2",
                    }
                if header != CONTRACT_COLUMNS:
                    old, new = cfg.schema_drift_rename
                    expected[SCHEMA_DRIFT] = {
                        "business_date": bdate.isoformat(),
                        "submitter_id": sub.submitter_id,
                        "file": f.name,
                        "missing_columns": [old],
                        "unexpected_columns": [new],
                        "change": "rename",
                        "affected_rows": len(rows),
                        "failed_task": "validate_schema",
                        "expected_agent": "data_quality",
                        "expected_severity": "S1",
                    }

            if DUPLICATES in cfg.anomalies and day == cfg.duplicate_day:
                resend = self._resend(files, bdate, expected)
                files.append(resend)
                resend_names.add(resend.name)

        if KEY_DRIFT in cfg.anomalies:
            # a resend replaces rows one for one, so the deduplicated row count excludes it
            total = sum(len(f.rows) for f in files if f.name not in resend_names)
            canonical = self.canonical[cfg.drift_location]
            expected[KEY_DRIFT] = {
                "location_id": cfg.drift_location,
                "canonical_outlet_id": canonical,
                "drifted_outlet_id": cfg.drift_outlet,
                "drifted_rows": self.drifted_rows,
                "rows_in_window": total,
                "drift_rate": round(self.drifted_rows / total, 4),
                "expected_agent": "reconciliation",
                "expected_severity": "S2" if self.drifted_rows / total > 0.02 else "S3",
            }

        dag_runs = self._dag_runs(files)
        expected["summary"] = {
            "seed": cfg.seed,
            "start": cfg.start.isoformat(),
            "days": cfg.days,
            "files": len(files),
            "rows": sum(len(f.rows) for f in files),
            "anomalies": sorted(cfg.anomalies),
        }
        return SyntheticPipeline(
            config=cfg, files=files, dag_runs=dag_runs, expected=expected, outlets=self.outlets
        )

    def _resend(
        self, files: list[LandingFile], bdate: date, expected: dict[str, Any]
    ) -> LandingFile:
        cfg, rng = self.cfg, self.rng
        original = next(
            f
            for f in files
            if f.submitter_id == cfg.duplicate_submitter and f.business_date == bdate
        )
        rows: list[list[str]] = []
        changed = 0
        for r in original.rows:
            r = list(r)
            if rng.random() < cfg.duplicate_changed_share:
                qty = int(r[5])
                unit = float(r[6]) / qty
                r[5] = str(qty + 1 if qty > 0 else qty - 1)
                r[6] = f"{unit * int(r[5]):.2f}"
                changed += 1
            rows.append(r)
        sub = next(s for s in SUBMITTERS if s.submitter_id == cfg.duplicate_submitter)
        produced = self._at(bdate, cfg.duplicate_resend_hhmm)
        resend = LandingFile(
            name=file_name(sub, bdate, cfg.duplicate_resend_hhmm),
            submitter_id=sub.submitter_id,
            business_date=bdate,
            produced_at=produced,
            landed_at=produced + timedelta(minutes=2),
            header=list(original.header),
            rows=rows,
        )
        expected[DUPLICATES] = {
            "business_date": bdate.isoformat(),
            "submitter_id": sub.submitter_id,
            "original_file": original.name,
            "resend_file": resend.name,
            "duplicate_keys": len(rows),
            "superseded_rows": len(rows),
            "changed_rows": changed,
            "resend_landed_after_dag": True,
            "expected_agent": "reconciliation",
            "expected_severity": "S2",
        }
        return resend

    def _dag_runs(self, files: list[LandingFile]) -> list[dict[str, Any]]:
        cfg, rng = self.cfg, self.rng
        runs = []
        for day in range(cfg.days):
            bdate = cfg.business_date(day)
            start = datetime(bdate.year, bdate.month, bdate.day, tzinfo=UTC) + timedelta(days=1)
            start += DAG_START
            todays = [
                f
                for f in files
                if f.business_date == bdate and f.landed_at <= start + timedelta(hours=6)
            ]
            on_time = [f for f in todays if f.landed_at <= start]
            last = max(f.landed_at for f in todays)
            # the sensor pokes every five minutes, so it notices a file on the next poke
            waited = max(timedelta(minutes=rng.randrange(1, 4)), last - start)
            poke = timedelta(minutes=5)
            sensor_end = start + (waited if last <= start else ((waited // poke) + 1) * poke)
            tasks: list[dict[str, Any]] = [
                {
                    "task_id": "wait_for_submitter_files",
                    "state": "success",
                    "try_number": 1,
                    "start": _iso(start),
                    "end": _iso(sensor_end),
                    "duration_s": int((sensor_end - start).total_seconds()),
                    "log": [
                        f"Poking for {len(SUBMITTERS)} submitter files for {bdate:%Y%m%d}",
                        f"{len(on_time)} of {len(SUBMITTERS)} present at start",
                    ]
                    + [
                        f"Found {f.name} (landed {_iso(f.landed_at)})"
                        for f in sorted(todays, key=lambda f: f.landed_at)
                    ],
                }
            ]
            clock = sensor_end
            failed = False
            loaded = [f for f in todays if f.landed_at <= sensor_end]
            for task_id in DAG_TASKS[1:]:
                if failed:
                    tasks.append(
                        {
                            "task_id": task_id,
                            "state": "upstream_failed",
                            "try_number": 0,
                            "start": None,
                            "end": None,
                            "duration_s": None,
                            "log": [],
                        }
                    )
                    continue
                lo, hi = TASK_DURATIONS[task_id]
                dur = timedelta(seconds=rng.randrange(lo, hi))
                task: dict[str, Any] = {
                    "task_id": task_id,
                    "state": "success",
                    "try_number": 1,
                    "start": _iso(clock),
                    "end": _iso(clock + dur),
                    "duration_s": int(dur.total_seconds()),
                    "log": [],
                }
                if task_id == "load_raw_transactions":
                    task["log"] = [
                        f"Loaded {len(f.rows)} rows from {f.name}, trailer count matches"
                        for f in loaded
                    ]
                elif task_id == "validate_schema":
                    bad = [f for f in loaded if f.header != CONTRACT_COLUMNS]
                    if bad:
                        f = bad[0]
                        missing = [c for c in CONTRACT_COLUMNS if c not in f.header]
                        unexpected = [c for c in f.header if c not in CONTRACT_COLUMNS]
                        task.update(state="failed")
                        task["log"] = [
                            f"Validating {len(loaded)} batches against contract raw.transactions",
                            f"ContractViolation: {f.name} missing {missing}; "
                            f"unexpected {unexpected}",
                            "Task failed with no retries remaining",
                        ]
                        failed = True
                    else:
                        task["log"] = [f"{len(loaded)} batches match contract raw.transactions"]
                elif task_id == "publish_metrics":
                    task["log"] = [f"{f.submitter_id} rows={len(f.rows)}" for f in loaded]
                tasks.append(task)
                clock += dur
            runs.append(
                {
                    "dag_id": DAG_ID,
                    "run_id": f"scheduled__{_iso(start)}",
                    "business_date": bdate.isoformat(),
                    "state": "failed" if failed else "success",
                    "start": _iso(start),
                    "end": _iso(clock),
                    "tasks": tasks,
                }
            )
        return runs


def generate(config: GeneratorConfig | None = None) -> SyntheticPipeline:
    return _Generator(config or GeneratorConfig()).run()
