from pathlib import Path

import pytest

from app.config import ROOT, Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        corpus_dir=ROOT / "corpus",
        index_dir=tmp_path / "index",
        embeddings_backend="hashing",
        llm_provider="none",
    )
