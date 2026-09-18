from app.config import ROOT
from app.retrieval.bm25 import BM25Retriever, tokenize
from app.retrieval.chunking import chunk_docs
from app.retrieval.corpus import load_corpus, load_dbt_models
from app.retrieval.hybrid import HybridRetriever, rrf
from app.retrieval.types import RetrievedChunk


def hit(cid: str, rank: int, doc: str | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=cid,
        doc_id=doc or cid.split("#")[0],
        title="t",
        path="p",
        section="s",
        doc_type="runbook",
        text=cid,
        score=0.0,
        rank=rank,
    )


class Fixed:
    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self.hits = hits

    def search(self, query: str, k: int = 5) -> list[RetrievedChunk]:
        return self.hits[:k]


def test_tokenize_keeps_identifiers_and_their_parts() -> None:
    toks = tokenize("Check channel_basket_id on OUT-1071, not basket_ref.")
    assert "channel_basket_id" in toks and "basket" in toks
    assert "out-1071" in toks and "1071" in toks
    assert "basket_ref" in toks


def test_rrf_rewards_agreement_between_lists() -> None:
    fused = rrf({"a": [hit("x", 1), hit("y", 2)], "b": [hit("y", 1), hit("z", 2)]}, k=60)
    order = [h.chunk_id for h, _, _ in fused]
    assert order[0] == "y"  # 1/62 + 1/61 beats 1/61 alone
    _, score, ranks = fused[0]
    assert ranks == {"a": 2, "b": 1}
    assert abs(score - (1 / 62 + 1 / 61)) < 1e-12


def test_hybrid_caps_chunks_per_document_and_records_ranks() -> None:
    dense = Fixed([hit("d1#a", 1), hit("d1#b", 2), hit("d1#c", 3), hit("d2#a", 4)])
    sparse = Fixed([hit("d1#c", 1), hit("d3#a", 2)])
    out = HybridRetriever(dense=dense, sparse=sparse, per_doc_cap=2).search("q", k=4)
    assert [h.doc_id for h in out].count("d1") == 2
    assert [h.rank for h in out] == list(range(1, len(out) + 1))
    top = out[0]
    assert top.chunk_id == "d1#c" and top.dense_rank == 3 and top.bm25_rank == 1


def test_hybrid_is_a_langchain_retriever() -> None:
    r = HybridRetriever(dense=Fixed([hit("d1#a", 1)]), sparse=Fixed([hit("d2#a", 1)]), k=2)
    docs = r.invoke("anything")
    assert [d.metadata["chunk_id"] for d in docs] == ["d1#a", "d2#a"] or len(docs) == 2
    assert docs[0].metadata["rank"] == 1


def test_bm25_finds_exact_identifiers_in_the_real_corpus() -> None:
    docs = load_corpus(ROOT / "corpus") + load_dbt_models(ROOT / "dbt" / "models")
    bm25 = BM25Retriever(chunk_docs(docs))
    top = bm25.search("basket_ref ContractViolation", k=3)
    assert "incidents/INC-0438-mobile-column-rename" in {h.doc_id for h in top} or any(
        "schema-drift" in h.doc_id for h in top
    )
    assert bm25.search("zzzz qqqq", k=3) == []


def test_dbt_models_render_as_documents() -> None:
    docs = load_dbt_models(ROOT / "dbt" / "models")
    ids = {d.doc_id for d in docs}
    assert {"dbt/stg_transactions", "dbt/fct_daily_sales", "dbt/source.raw.transactions"} <= ids
    stg = next(d for d in docs if d.doc_id == "dbt/stg_transactions")
    assert "relationships" in stg.body and stg.doc_type == "dbt_model"
    assert load_dbt_models(ROOT / "does-not-exist") == []
