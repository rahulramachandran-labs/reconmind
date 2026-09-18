import numpy as np

from app.retrieval.embeddings import (
    HashingEmbeddings,
    SentenceTransformerEmbeddings,
    build_embeddings,
)


def test_hashing_embeddings_are_deterministic_and_normalized() -> None:
    emb = HashingEmbeddings(dim=64)
    a = emb.embed_query("duplicate submissions latest file wins")
    assert a == emb.embed_query("duplicate submissions latest file wins")
    assert abs(np.linalg.norm(a) - 1.0) < 1e-6


def test_hashing_embeddings_rank_overlap_higher() -> None:
    emb = HashingEmbeddings()
    q = np.array(emb.embed_query("schema drift renamed column"))
    near, far = (
        np.array(v)
        for v in emb.embed_documents(
            ["a renamed column is schema drift", "volume dropped below trailing average"]
        )
    )
    assert q @ near > q @ far


def test_empty_text_gives_zero_vector() -> None:
    assert not any(HashingEmbeddings(dim=8).embed_query("  "))


def test_factory_picks_backend() -> None:
    assert isinstance(build_embeddings("hashing", "x"), HashingEmbeddings)
    st = build_embeddings("sentence-transformers", "some/model")
    assert isinstance(st, SentenceTransformerEmbeddings)
    assert st._model is None, "model must load lazily"


def test_openai_embeddings_batch_requests() -> None:
    from types import SimpleNamespace

    from app.retrieval.embeddings import OpenAIEmbeddings

    calls: list[int] = []

    def create(model: str, input: list[str]) -> object:
        calls.append(len(input))
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2]) for _ in input])

    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    emb = build_embeddings("openai", "text-embedding-3-small", client)
    assert isinstance(emb, OpenAIEmbeddings)
    assert len(emb.embed_documents(["x"] * 300)) == 300
    assert calls == [256, 44]
    assert emb.embed_query("q") == [0.1, 0.2]


def test_openai_embeddings_need_a_client() -> None:
    import pytest

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        build_embeddings("openai", "m")


def test_fastembed_loads_lazily() -> None:
    from app.retrieval.embeddings import FastEmbedEmbeddings

    emb = build_embeddings("fastembed", "sentence-transformers/all-MiniLM-L6-v2")
    assert isinstance(emb, FastEmbedEmbeddings) and emb._model is None

    class FakeModel:
        def embed(self, texts: list[str], batch_size: int) -> list[list[float]]:
            return [[1.0, 0.0] for _ in texts]

    emb._model = FakeModel()
    assert emb.embed_query("x") == [1.0, 0.0]


def test_reranker_orders_by_score_and_renumbers() -> None:
    from app.retrieval.rerank import CrossEncoderReranker, build_reranker
    from app.retrieval.types import RetrievedChunk

    hits = [
        RetrievedChunk(
            chunk_id=f"c{i}",
            doc_id="d",
            title="t",
            path="p",
            section="s",
            doc_type="runbook",
            text=f"text {i}",
            score=0.0,
            rank=i + 1,
        )
        for i in range(4)
    ]

    class Fake(CrossEncoderReranker):
        def _scores(self, query: str, texts: list[str]) -> list[float]:
            return [0.0, 3.0, -1.0, 1.0]

    out = Fake("m").rerank("q", hits, 3)
    assert [h.chunk_id for h in out] == ["c1", "c3", "c0"]
    assert [h.rank for h in out] == [1, 2, 3] and 0.9 < out[0].score < 1
    assert Fake("m").rerank("q", [], 3) == []
    assert build_reranker("none", "sentence-transformers", "m") is None
    fe = build_reranker("cross-encoder", "fastembed", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    assert fe is not None and fe.model_name == "Xenova/ms-marco-MiniLM-L-6-v2"  # type: ignore[attr-defined]
