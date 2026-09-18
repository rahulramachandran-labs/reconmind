from typing import Any, Protocol

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict

from app.retrieval.types import RetrievedChunk


class Searcher(Protocol):
    def search(self, query: str, k: int = 5) -> list[RetrievedChunk]: ...


def rrf(
    ranked_lists: dict[str, list[RetrievedChunk]], k: int = 60
) -> list[tuple[RetrievedChunk, float, dict[str, int]]]:
    """Reciprocal rank fusion: score = sum over lists of 1 / (k + rank).

    Only ranks matter, so BM25 scores and cosine similarities never have to be
    put on the same scale.
    """
    fused: dict[str, float] = {}
    first_seen: dict[str, RetrievedChunk] = {}
    ranks: dict[str, dict[str, int]] = {}
    for name, hits in ranked_lists.items():
        for hit in hits:
            fused[hit.chunk_id] = fused.get(hit.chunk_id, 0.0) + 1.0 / (k + hit.rank)
            first_seen.setdefault(hit.chunk_id, hit)
            ranks.setdefault(hit.chunk_id, {})[name] = hit.rank
    order = sorted(fused, key=lambda cid: (-fused[cid], cid))
    return [(first_seen[cid], fused[cid], ranks[cid]) for cid in order]


class HybridRetriever(BaseRetriever):
    """BM25 and dense search fused with RRF, as a LangChain retriever.

    ``per_doc_cap`` can stop one document from filling every slot. It is off by
    default: on the golden set a cap of two cost eight points of recall, because
    questions about one incident legitimately need several of its sections.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    dense: Any
    sparse: Any
    k: int = 5
    candidates: int = 20
    rrf_k: int = 60
    per_doc_cap: int | None = None

    def search(self, query: str, k: int | None = None) -> list[RetrievedChunk]:
        k = k or self.k
        lists = {
            "dense": self.dense.search(query, self.candidates),
            "bm25": self.sparse.search(query, self.candidates),
        }
        out: list[RetrievedChunk] = []
        per_doc: dict[str, int] = {}
        for hit, score, ranks in rrf(lists, self.rrf_k):
            if self.per_doc_cap and per_doc.get(hit.doc_id, 0) >= self.per_doc_cap:
                continue
            per_doc[hit.doc_id] = per_doc.get(hit.doc_id, 0) + 1
            out.append(
                hit.model_copy(
                    update={
                        "score": round(score, 5),
                        "rank": len(out) + 1,
                        "dense_rank": ranks.get("dense"),
                        "bm25_rank": ranks.get("bm25"),
                    }
                )
            )
            if len(out) == k:
                break
        return out

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        return [
            Document(page_content=c.text, metadata=c.model_dump(exclude={"text"}))
            for c in self.search(query)
        ]
