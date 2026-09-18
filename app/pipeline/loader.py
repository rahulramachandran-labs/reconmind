"""Load landing files into Postgres the way the ``load_raw_transactions`` task does.

Columns are mapped by name. A contracted column missing from a file lands as
null and is recorded on ``file_loads``; an unknown column is recorded and
dropped. Files already in ``file_loads`` are skipped, so reloading is safe.
"""

import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, insert, select

from app.db.models import (
    AuditLedger,
    FileLoad,
    OutletLocationMap,
    SubmitterRegistry,
    Transaction,
)
from app.db.session import session_scope
from app.pipeline.synthetic import CONTRACT_COLUMNS, parse_file_name

log = logging.getLogger(__name__)


@dataclass
class LoadStats:
    files: int = 0
    rows: int = 0
    skipped: int = 0


@dataclass
class ParsedFile:
    name: str
    header: list[str]
    records: list[dict[str, Any]]
    trailer_count: int | None
    missing: list[str]
    unexpected: list[str]


def _ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def parse_landing_file(path: Path) -> ParsedFile:
    lines = path.read_text(encoding="utf-8").splitlines()
    header = lines[0].split("|")
    trailer = None
    body = lines[1:]
    if body and body[-1].startswith("TRAILER|"):
        trailer = int(body[-1].split("|", 1)[1])
        body = body[:-1]
    missing = [c for c in CONTRACT_COLUMNS if c not in header]
    unexpected = [c for c in header if c not in CONTRACT_COLUMNS]
    records = []
    for line in body:
        raw = dict(zip(header, line.split("|"), strict=True))
        rec: dict[str, Any] = {c: raw.get(c) for c in CONTRACT_COLUMNS}
        rec["qty"] = int(rec["qty"]) if rec["qty"] is not None else None
        rec["amount"] = Decimal(rec["amount"]) if rec["amount"] is not None else None
        rec["event_ts"] = _ts(rec["event_ts"]) if rec["event_ts"] is not None else None
        rec["submitter_file_name"] = path.name
        records.append(rec)
    return ParsedFile(path.name, header, records, trailer, missing, unexpected)


def load_reference(engine: Engine, sample_dir: Path) -> None:
    ref = sample_dir / "reference"
    with session_scope(engine) as s:
        if s.scalar(select(SubmitterRegistry.submitter_id).limit(1)) is None:
            with (ref / "submitter_registry.csv").open() as fh:
                for row in csv.DictReader(fh):
                    s.add(
                        SubmitterRegistry(
                            submitter_id=row["submitter_id"],
                            submitter_name=row["submitter_name"],
                            channel=row["channel"],
                            expected_daily_files=int(row["expected_daily_files"]),
                            sla_hhmm=row["sla_hhmm"],
                            contact=row["contact"],
                        )
                    )
        if s.scalar(select(OutletLocationMap.outlet_id).limit(1)) is None:
            with (ref / "outlet_location_map.csv").open() as fh:
                for row in csv.DictReader(fh):
                    s.add(
                        OutletLocationMap(
                            outlet_id=row["outlet_id"],
                            location_id=row["location_id"],
                            valid_from=datetime.fromisoformat(row["valid_from"]).date(),
                            valid_to=None,
                        )
                    )


def load_pipeline(engine: Engine, sample_dir: Path, actor: str = "loader") -> LoadStats:
    load_reference(engine, sample_dir)
    arrivals: dict[str, dict[str, str]] = {}
    with (sample_dir / "reference" / "file_arrivals.csv").open() as fh:
        for row in csv.DictReader(fh):
            arrivals[row["file_name"]] = row

    stats = LoadStats()
    with session_scope(engine) as s:
        done = set(s.scalars(select(FileLoad.file_name)))
    # load in landing order, the way the nightly job would have seen them
    ordered = sorted(arrivals.values(), key=lambda r: (r["landed_at"], r["file_name"]))
    for arrival in ordered:
        name = arrival["file_name"]
        if name in done:
            stats.skipped += 1
            continue
        parsed = parse_landing_file(sample_dir / "landing" / name)
        submitter_id, business_date, _, _ = parse_file_name(name)
        with session_scope(engine) as s:
            if parsed.records:
                s.execute(insert(Transaction), parsed.records)
            s.add(
                FileLoad(
                    file_name=name,
                    submitter_id=submitter_id,
                    business_date=business_date,
                    produced_at=_ts(arrival["produced_at"]),
                    landed_at=_ts(arrival["landed_at"]),
                    row_count=len(parsed.records),
                    trailer_count=parsed.trailer_count,
                    header=parsed.header,
                    missing_columns=parsed.missing,
                    unexpected_columns=parsed.unexpected,
                )
            )
            s.add(
                AuditLedger(
                    actor=actor,
                    action="file.loaded",
                    subject=name,
                    payload={
                        "rows": len(parsed.records),
                        "trailer_count": parsed.trailer_count,
                        "missing_columns": parsed.missing,
                        "unexpected_columns": parsed.unexpected,
                    },
                )
            )
        stats.files += 1
        stats.rows += len(parsed.records)
    log.info("load complete", extra={"files": stats.files, "rows": stats.rows})
    return stats
