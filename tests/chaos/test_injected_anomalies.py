"""Chaos suite: plant one anomaly at a time and make sure the right agent catches it.

Each case regenerates a small pipeline with the generator, loads it into a
fresh database, runs a full scan and compares the findings with what the
generator says it planted. A clean pipeline must produce no findings at all.
"""

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.core.config import ROOT, Settings
from app.pipeline.artifacts import write_sample
from app.pipeline.loader import load_pipeline
from app.pipeline.synthetic import ALL_ANOMALIES, GeneratorConfig, generate
from tests.integration.agent_fixtures import retail_service

pytestmark = pytest.mark.chaos


def _fresh(db_url: str) -> Engine:
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("drop schema public cascade"))
        conn.execute(text("create schema public"))
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["url"] = db_url
    command.upgrade(cfg, "head")
    return engine


@pytest.fixture
def planted(
    db_url: str, tmp_path: Path, request: pytest.FixtureRequest
) -> Iterator[tuple[Engine, dict, Path]]:
    anomalies = frozenset(request.param)
    pipeline = generate(GeneratorConfig(seed=7, rows_per_day=160, anomalies=anomalies))
    sample = tmp_path / "sample"
    write_sample(pipeline, sample)
    engine = _fresh(db_url)
    load_pipeline(engine, sample)
    yield engine, pipeline.expected, sample / "airflow" / "dag_runs.json"
    engine.dispose()


async def _scan(
    engine: Engine, settings: Settings, dag_runs: Path, monkeypatch: pytest.MonkeyPatch
) -> list[dict]:
    monkeypatch.setenv("DAG_RUNS_PATH", str(dag_runs))
    async with retail_service(engine, settings) as svc:
        return await svc.run_to_end(svc.run("scan"))


@pytest.mark.parametrize(
    "planted", [[a] for a in sorted(ALL_ANOMALIES)], indirect=True, ids=sorted(ALL_ANOMALIES)
)
async def test_each_anomaly_is_caught_by_the_right_agent(
    planted: tuple[Engine, dict, Path], settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, expected, dag_runs = planted
    [(kind, spec)] = [(k, v) for k, v in expected.items() if k != "summary"]
    events = await _scan(engine, settings, dag_runs, monkeypatch)
    findings = [e for e in events if e["type"] == "finding"]
    assert [(f["finding_type"], f["specialist"], f["severity"]) for f in findings] == [
        (kind, spec["expected_agent"], spec["expected_severity"])
    ]


@pytest.mark.parametrize("planted", [[]], indirect=True, ids=["clean"])
async def test_a_clean_pipeline_raises_nothing(
    planted: tuple[Engine, dict, Path], settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, _, dag_runs = planted
    events = await _scan(engine, settings, dag_runs, monkeypatch)
    assert [e for e in events if e["type"] == "finding"] == []
    assert events[-1]["type"] == "done"


@pytest.mark.parametrize("planted", [sorted(ALL_ANOMALIES)], indirect=True, ids=["all"])
async def test_full_investigation_fits_the_latency_budget(
    planted: tuple[Engine, dict, Path], settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Demo mode (no paid model) must finish a whole scan inside 30 seconds."""
    engine, _, dag_runs = planted
    start = time.perf_counter()
    events = await _scan(engine, settings, dag_runs, monkeypatch)
    elapsed = time.perf_counter() - start
    assert {e["finding_type"] for e in events if e["type"] == "finding"} == set(ALL_ANOMALIES)
    assert elapsed < 30, f"scan took {elapsed:.1f}s"
