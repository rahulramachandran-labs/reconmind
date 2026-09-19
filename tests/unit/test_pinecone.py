from typing import Any

from app.core.config import ROOT
from app.retrieval.chunking import chunk_docs
from app.retrieval.corpus import load_corpus
from app.retrieval.embeddings import HashingEmbeddings
from app.retrieval.pinecone_store import PineconeRetriever


class FakeIndex:
    def __init__(self, existing: int = 0) -> None:
        self.vectors: dict[str, list[float]] = {}
        self.existing = existing
        self.upserts = 0

    def describe_index_stats(self) -> dict[str, Any]:
        return {"namespaces": {"ns": {"vector_count": self.existing}}} if self.existing else {}

    def upsert(self, vectors: list[dict[str, Any]], namespace: str) -> None:
        self.upserts += 1
        for v in vectors:
            self.vectors[v["id"]] = v["values"]

    def query(
        self, vector: list[float], top_k: int, namespace: str, include_metadata: bool
    ) -> dict[str, Any]:
        scored = sorted(
            (
                (sum(a * b for a, b in zip(vector, v, strict=True)), cid)
                for cid, v in self.vectors.items()
            ),
            reverse=True,
        )[:top_k]
        return {
            "matches": [{"id": cid, "score": s} for s, cid in scored] + [{"id": "gone", "score": 0}]
        }


def test_upserts_once_and_maps_matches_back_to_chunks() -> None:
    chunks = chunk_docs(load_corpus(ROOT / "corpus"))
    index = FakeIndex()
    r = PineconeRetriever(chunks, HashingEmbeddings(), index, "ns", batch=50)
    assert len(index.vectors) == len(chunks) and index.upserts == 2
    hits = r.search("latest submitter file wins on a resend", k=3)
    assert len(hits) == 3 and [h.rank for h in hits] == [1, 2, 3]


def test_skips_upsert_when_namespace_is_already_full() -> None:
    chunks = chunk_docs(load_corpus(ROOT / "corpus"))
    index = FakeIndex(existing=len(chunks))
    PineconeRetriever(chunks, HashingEmbeddings(), index, "ns")
    assert index.upserts == 0
