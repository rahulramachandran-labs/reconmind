import json

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from app.core.config import ROOT
from app.db.models import AuditLedger
from app.db.session import get_engine, normalize_url, ping, session_scope
from app.memory.sessions import SqlSessionStore
from app.pipeline.loader import load_pipeline, parse_landing_file

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


def test_migration_0004_folds_findings_duplicated_before_fingerprints(
    db_url: str, migrated_engine: Engine
) -> None:
    from uuid import uuid4

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["url"] = db_url
    command.downgrade(cfg, "0003")
    runs = [uuid4() for _ in range(3)]
    s1 = [uuid4() for _ in runs]
    s2 = [uuid4(), uuid4()]
    with migrated_engine.begin() as conn:
        for age, run in zip((3, 2, 1), runs, strict=True):
            conn.execute(
                text(
                    "insert into agent_runs (id, trigger, adapter, status, plan, prompt_tokens,"
                    " completion_tokens, cost_usd, started_at) values (:id, 'scan',"
                    " 'retail_recon', 'paused_review', '{}', 0, 0, 0,"
                    " now() - make_interval(hours => :age))"
                ),
                {"id": run, "age": age},
            )

        def report(rid, run, age, severity, status, title, seen=1):  # type: ignore[no-untyped-def]
            conn.execute(
                text(
                    "insert into incident_reports (id, run_id, finding_type, severity, title,"
                    " status, report, created_at, fingerprint, seen_count, last_seen_at)"
                    " values (:id, :run, 'x', :sev, :title, :status, '{}',"
                    " now() - make_interval(hours => :age), 'x:' || :title, :seen,"
                    " now() - make_interval(hours => :age))"
                ),
                {
                    "id": rid,
                    "run": run,
                    "age": age,
                    "sev": severity,
                    "status": status,
                    "title": title,
                    "seen": seen,
                },
            )

        for rid, run, age, seen in zip(s1, runs, (3, 2, 1), (1, 1, 2), strict=True):
            report(rid, run, age, "S1", "pending_review", "renamed a column", seen)
        report(s2[0], runs[0], 3, "S2", "published", "resent a file")
        report(s2[1], runs[1], 2, "S2", "published", "resent a file")
    command.upgrade(cfg, "head")

    with migrated_engine.connect() as conn:
        rows = {
            r.id: r
            for r in conn.execute(
                text("select id, duplicate_of, seen_count, last_seen_at from incident_reports")
            )
        }
        status = dict(conn.execute(text("select id, status from agent_runs")).all())
        merged = conn.scalar(
            text("select count(*) from audit_ledger where action = 'finding.merged'")
        )
    # the first report of each finding stays, carrying every sighting
    assert rows[s1[0]].duplicate_of is None and rows[s1[0]].seen_count == 4
    assert rows[s1[0]].last_seen_at == max(rows[i].last_seen_at for i in s1)
    assert rows[s1[1]].duplicate_of == rows[s1[2]].duplicate_of == s1[0]
    assert rows[s2[1]].duplicate_of == s2[0] and rows[s2[0]].seen_count == 2
    # the first run still carries the review; the runs waiting only on copies are superseded
    assert status[runs[0]] == "paused_review"
    assert status[runs[1]] == status[runs[2]] == "superseded"
    assert merged == 3
