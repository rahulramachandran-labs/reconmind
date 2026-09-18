from dataclasses import dataclass

from langchain_core.documents import Document

from app.config import Settings
from app.retrieval.chunking import chunk_docs
from app.retrieval.corpus import SourceDoc, load_corpus
from app.retrieval.dense import DenseRetriever
from app.retrieval.embeddings import build_embeddings
from app.retrieval.types import RetrievedChunk


@dataclass
class RetrievalService:
    docs: list[SourceDoc]
    chunks: list[Document]
    dense: DenseRetriever

    @classmethod
    def from_settings(cls, settings: Settings) -> "RetrievalService":
        docs = load_corpus(settings.corpus_dir)
        chunks = chunk_docs(docs)
        embeddings = build_embeddings(settings.embeddings_backend, settings.embeddings_model)
        cache = settings.index_dir if settings.embeddings_backend != "hashing" else None
        dense = DenseRetriever.build(
            chunks, embeddings, cache_dir=cache, model_name=settings.embeddings_model
        )
        return cls(docs=docs, chunks=chunks, dense=dense)

    def search(self, query: str, k: int = 5) -> list[RetrievedChunk]:
        return self.dense.search(query, k)
