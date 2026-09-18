"""Runs against the real MiniLM model. Catches regressions in chunking that the
hashing embedder in the other tests would never notice."""

from pathlib import Path

import pytest

from app.config import ROOT, Settings
from app.retrieval.service import RetrievalService

pytestmark = pytest.mark.model

CASES = [
    (
        "which copy wins when a submitter sends the same file twice",
        {"runbooks/duplicate-submissions"},
    ),
    (
        "one store is reporting under two different outlet ids",
        {"runbooks/key-drift-outlet-location", "incidents/INC-0412-outlet-id-transposition"},
    ),
    (
        "the mobile export renamed a column and validate_schema failed",
        {"incidents/INC-0438-mobile-column-rename", "runbooks/schema-drift"},
    ),
    ("row count far below the trailing seven day average", {"runbooks/volume-anomalies"}),
]


@pytest.fixture(scope="module")
def service(tmp_path_factory: pytest.TempPathFactory) -> RetrievalService:
    s = Settings(
        _env_file=None, corpus_dir=ROOT / "corpus", index_dir=tmp_path_factory.mktemp("idx")
    )
    return RetrievalService.from_settings(s)


@pytest.mark.parametrize(("query", "relevant"), CASES)
def test_relevant_document_in_top_three(
    service: RetrievalService, query: str, relevant: set[str]
) -> None:
    top = {c.doc_id for c in service.search(query, k=3)}
    assert top & relevant


def test_index_is_cached_on_disk(service: RetrievalService, tmp_path: Path) -> None:
    s = Settings(_env_file=None, corpus_dir=ROOT / "corpus", index_dir=tmp_path)
    RetrievalService.from_settings(s)
    assert list(tmp_path.glob("*/index.faiss"))
    again = RetrievalService.from_settings(s)
    assert len(again.chunks) == len(service.chunks)
