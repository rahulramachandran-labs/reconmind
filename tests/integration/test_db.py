import json

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from app.config import ROOT
from app.db.models import AuditLedger
from app.db.session import get_engine, normalize_url, ping, session_scope
from app.pipeline.loader import load_pipeline, parse_landing_file
from app.sessions import SqlSessionStore

SAMPLE = ROOT / "data" / "sample"
EXPECTED = json.loads((SAMPLE / "expected_anomalies.json").read_text())


def test_normalize_url() -> None:
    assert normalize_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("postgresql+psycopg://x") == "postgresql+psycopg://x"


def test_parse_landing_file_maps_by_name() -> None:
    parsed = parse_landing_file(SAMPLE / "landing" / EXPECTED["schema_drift"]["file"])
    assert parsed.missing == ["channel_basket_id"] and parsed.unexpected == ["basket_ref"]
    assert parsed.trailer_count == len(parsed.records)
    assert all(r["channel_basket_id"] is None for r in parsed.records)


def test_ledger_rejects_update_delete_and_truncate(migrated_engine: Engine) -> None:
    with session_scope(migrated_engine) as s:
        s.add(AuditLedger(actor="test", action="finding.created", subject="x", payload={}))
    for stmt in (
        "update audit_ledger set actor = 'someone else'",
        "delete from audit_ledger",
        "truncate audit_ledger",
    ):
        with pytest.raises(DBAPIError, match="append-only"), migrated_engine.begin() as conn:
            conn.execute(text(stmt))
    with migrated_engine.connect() as conn:
        assert conn.scalar(text("select count(*) from audit_ledger")) == 1
        # appends still work
    with session_scope(migrated_engine) as s:
        s.add(AuditLedger(actor="test", action="finding.corrected", subject="x", payload={"of": 1}))


def test_loader_loads_sample_once_and_records_drift(migrated_engine: Engine) -> None:
    stats = load_pipeline(migrated_engine, SAMPLE)
    summary = EXPECTED["summary"]
    assert stats.files == summary["files"] and stats.rows == summary["rows"]
    again = load_pipeline(migrated_engine, SAMPLE)
    assert again.files == 0 and again.skipped == summary["files"]
    with migrated_engine.connect() as conn:
        assert conn.scalar(text("select count(*) from transactions")) == summary["rows"]
        missing = conn.execute(
            text(
                "select file_name, missing_columns, unexpected_columns from file_loads "
                "where cardinality(missing_columns) > 0"
            )
        ).all()
        assert [tuple(r) for r in missing] == [
            (EXPECTED["schema_drift"]["file"], ["channel_basket_id"], ["basket_ref"])
        ]
        assert (
            conn.scalar(text("select count(*) from audit_ledger where action = 'file.loaded'"))
            == summary["files"]
        )
        assert conn.scalar(text("select count(*) from submitter_registry")) == 4
        assert conn.scalar(text("select count(*) from outlet_location_map")) == 40


def test_detection_queries_from_the_runbooks_find_the_planted_numbers(
    migrated_engine: Engine,
) -> None:
    load_pipeline(migrated_engine, SAMPLE)
    dup = EXPECTED["duplicate_submission"]
    with migrated_engine.connect() as conn:
        superseded = conn.scalar(text("""
            with ranked as (
              select row_number() over (
                partition by transaction_id, channel_basket_id, upc_code
                order by split_part(submitter_file_name, '_', 2)
                         || split_part(submitter_file_name, '_', 3) desc,
                         submitter_file_name desc) as rn
              from transactions where channel_basket_id is not null)
            select count(*) from ranked where rn > 1"""))
        assert superseded == dup["superseded_rows"]
        drifted = conn.scalar(
            text("""
            select count(*) from transactions t
            left join outlet_location_map m on m.outlet_id = t.outlet_id
            where m.outlet_id is null and t.submitter_file_name <> :resend"""),
            {"resend": dup["resend_file"]},
        )
        assert drifted == EXPECTED["key_drift"]["drifted_rows"]


def test_sql_session_store(migrated_engine: Engine) -> None:
    store = SqlSessionStore(migrated_engine)
    sid = store.create("how does dedup work")
    store.append(sid, "user", "how does dedup work")
    store.append(sid, "assistant", "latest file wins [1]", {"provider": "extractive"})
    hist = store.history(sid)
    assert [m.role for m in hist] == ["user", "assistant"]
    assert hist[1].meta == {"provider": "extractive"}
    assert store.exists(sid)


def test_ping_and_engine_cache(db_url: str) -> None:
    engine = get_engine(db_url)
    assert ping(engine) and get_engine(db_url) is engine
    assert not ping(get_engine("postgresql+psycopg://nobody:x@127.0.0.1:1/none"))
