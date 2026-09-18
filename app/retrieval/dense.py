import hashlib
import json
import logging
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_community.vectorstores.utils import DistanceStrategy
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.retrieval.types import RetrievedChunk

log = logging.getLogger(__name__)


def fingerprint(chunks: list[Document], model_name: str) -> str:
    h = hashlib.sha256(model_name.encode())
    for c in chunks:
        h.update(c.metadata["chunk_id"].encode())
        h.update(c.page_content.encode())
    return h.hexdigest()[:16]


class DenseRetriever:
    def __init__(self, store: FAISS) -> None:
        self.store = store

    @classmethod
    def build(
        cls,
        chunks: list[Document],
        embeddings: Embeddings,
        cache_dir: Path | None = None,
        model_name: str = "",
    ) -> "DenseRetriever":
        target = cache_dir / fingerprint(chunks, model_name) if cache_dir else None
        if target and (target / "index.faiss").exists():
            # only ever loads an index this process family wrote itself
            store = FAISS.load_local(str(target), embeddings, allow_dangerous_deserialization=True)
            log.info("loaded dense index", extra={"path": str(target)})
            return cls(store)
        store = FAISS.from_documents(
            chunks, embeddings, distance_strategy=DistanceStrategy.MAX_INNER_PRODUCT
        )
        if target:
            target.mkdir(parents=True, exist_ok=True)
            store.save_local(str(target))
            (target / "meta.json").write_text(
                json.dumps({"model": model_name, "chunks": len(chunks)})
            )
            log.info("built dense index", extra={"path": str(target), "chunks": len(chunks)})
        return cls(store)

    def search(self, query: str, k: int = 5) -> list[RetrievedChunk]:
        hits = self.store.similarity_search_with_score(query, k=k)
        return [to_chunk(doc, float(score), rank) for rank, (doc, score) in enumerate(hits, 1)]


def to_chunk(doc: Document, score: float, rank: int) -> RetrievedChunk:
    m = doc.metadata
    return RetrievedChunk(
        chunk_id=m["chunk_id"],
        doc_id=m["doc_id"],
        title=m["title"],
        path=m["path"],
        section=m["section"],
        doc_type=m["doc_type"],
        text=doc.page_content,
        score=round(score, 4),
        rank=rank,
    )
