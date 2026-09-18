import logging
from dataclasses import dataclass, field
from typing import Any

from langchain_core.documents import Document

from app.config import Settings
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.chunking import chunk_docs
from app.retrieval.corpus import SourceDoc, load_corpus, load_dbt_models
from app.retrieval.dense import DenseRetriever, fingerprint
from app.retrieval.embeddings import build_embeddings
from app.retrieval.hybrid import HybridRetriever, Searcher
from app.retrieval.types import RetrievedChunk

log = logging.getLogger(__name__)


@dataclass
class RetrievalService:
    docs: list[SourceDoc]
    chunks: list[Document]
    dense: Searcher
    bm25: BM25Retriever
    mode: str = "hybrid"
    hybrid: HybridRetriever = field(init=False)

    def __post_init__(self) -> None:
        self.hybrid = HybridRetriever(dense=self.dense, sparse=self.bm25)

    @classmethod
    def from_settings(cls, settings: Settings, openai_client: Any = None) -> "RetrievalService":
        docs = load_corpus(settings.corpus_dir) + load_dbt_models(settings.dbt_models_dir)
        chunks = chunk_docs(docs)
        model = (
            settings.openai_embeddings_model
            if settings.embeddings_backend == "openai"
            else settings.embeddings_model
        )
        if settings.embeddings_backend == "openai" and openai_client is None:
            from openai import OpenAI

            key = settings.openai_api_key.get_secret_value() if settings.openai_api_key else None
            openai_client = OpenAI(api_key=key) if key else None
        embeddings = build_embeddings(settings.embeddings_backend, model, openai_client)
        dense: Searcher
        if settings.vector_store == "pinecone":
            from app.retrieval.pinecone_store import PineconeRetriever, open_index

            if not settings.pinecone_api_key:
                raise ValueError("VECTOR_STORE=pinecone needs PINECONE_API_KEY")
            dim = len(embeddings.embed_query("dimension probe"))
            index = open_index(
                settings.pinecone_api_key.get_secret_value(), settings.pinecone_index, dim
            )
            dense = PineconeRetriever(chunks, embeddings, index, fingerprint(chunks, model))
        else:
            cache = settings.index_dir if settings.embeddings_backend != "hashing" else None
            dense = DenseRetriever.build(chunks, embeddings, cache_dir=cache, model_name=model)
        log.info(
            "retrieval ready",
            extra={"docs": len(docs), "chunks": len(chunks), "mode": settings.retriever},
        )
        return cls(
            docs=docs,
            chunks=chunks,
            dense=dense,
            bm25=BM25Retriever(chunks),
            mode=settings.retriever,
        )

    def search(self, query: str, k: int = 5, mode: str | None = None) -> list[RetrievedChunk]:
        mode = mode or self.mode
        if mode == "dense":
            return self.dense.search(query, k)
        if mode == "bm25":
            return self.bm25.search(query, k)
        return self.hybrid.search(query, k)

    def document(self, doc_id: str) -> SourceDoc | None:
        return next((d for d in self.docs if d.doc_id == doc_id), None)
