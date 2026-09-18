"""Pinecone as the dense side, behind VECTOR_STORE=pinecone.

Only chunk ids travel to Pinecone as metadata; the text stays local and is
looked up by id, so the index never holds more than it needs to.
"""

import logging
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from app.retrieval.dense import to_chunk
from app.retrieval.types import RetrievedChunk

log = logging.getLogger(__name__)


class PineconeRetriever:
    def __init__(
        self,
        chunks: list[Document],
        embeddings: Embeddings,
        index: Any,
        namespace: str,
        batch: int = 100,
    ) -> None:
        self.embeddings = embeddings
        self.index = index
        self.namespace = namespace
        self.by_id = {c.metadata["chunk_id"]: c for c in chunks}
        stats = index.describe_index_stats()
        existing = (stats.get("namespaces") or {}).get(namespace, {}).get("vector_count", 0)
        if existing != len(chunks):
            vectors = embeddings.embed_documents([c.page_content for c in chunks])
            items = [
                {
                    "id": c.metadata["chunk_id"],
                    "values": v,
                    "metadata": {"doc_id": c.metadata["doc_id"]},
                }
                for c, v in zip(chunks, vectors, strict=True)
            ]
            for i in range(0, len(items), batch):
                index.upsert(vectors=items[i : i + batch], namespace=namespace)
            log.info("upserted to pinecone", extra={"namespace": namespace, "vectors": len(items)})

    def search(self, query: str, k: int = 5) -> list[RetrievedChunk]:
        res = self.index.query(
            vector=self.embeddings.embed_query(query),
            top_k=k,
            namespace=self.namespace,
            include_metadata=False,
        )
        hits: list[RetrievedChunk] = []
        for match in res.get("matches", []):
            doc = self.by_id.get(match["id"])
            if doc is not None:
                hits.append(to_chunk(doc, float(match["score"]), len(hits) + 1))
        return hits


def open_index(api_key: str, name: str, dimension: int) -> Any:  # pragma: no cover - network
    from pinecone import Pinecone, ServerlessSpec

    pc = Pinecone(api_key=api_key)
    if name not in pc.list_indexes().names():
        pc.create_index(
            name=name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    return pc.Index(name)
