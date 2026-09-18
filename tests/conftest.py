import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from app.config import ROOT, Settings
from app.db.session import normalize_url


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        corpus_dir=ROOT / "corpus",
        dbt_models_dir=ROOT / "dbt" / "models",
        index_dir=tmp_path / "index",
        embeddings_backend="hashing",
        llm_providers=[],
        database_url=None,
        agents_enabled=False,
    )


def _test_db_url() -> str | None:
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        env = ROOT / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                if line.startswith("DATABASE_URL="):
                    url = line.split("=", 1)[1].strip()
    if not url:
        return None
    u = make_url(normalize_url(url))
    return u.set(database=(u.database or "reconmind") + "_test").render_as_string(
        hide_password=False
    )


@pytest.fixture(scope="session")
def db_url() -> str:
    url = _test_db_url()
    if url is None:
        pytest.skip("no database configured")
    u = make_url(url)
    admin = create_engine(u.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.scalar(
                text("select 1 from pg_database where datname = :n"), {"n": u.database}
            )
            if not exists:
                conn.execute(text(f'create database "{u.database}"'))
    except Exception as exc:
        pytest.skip(f"database unreachable: {exc}")
    finally:
        admin.dispose()
    return url


@pytest.fixture
def migrated_engine(db_url: str) -> Iterator[Engine]:
    """A freshly migrated database for each test that asks for one."""
    from alembic import command
    from alembic.config import Config

    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("drop schema public cascade"))
        conn.execute(text("create schema public"))
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["url"] = db_url
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def loaded_engine(db_url: str) -> Iterator[Engine]:
    """Migrated and loaded with the committed sample, once per test module."""
    from alembic import command
    from alembic.config import Config

    from app.pipeline.loader import load_pipeline

    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("drop schema public cascade"))
        conn.execute(text("create schema public"))
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.attributes["url"] = db_url
    command.upgrade(cfg, "head")
    load_pipeline(engine, ROOT / "data" / "sample")
    yield engine
    engine.dispose()
