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
