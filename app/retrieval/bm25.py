import re

from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from app.retrieval.dense import to_chunk
from app.retrieval.types import RetrievedChunk

_TOKEN = re.compile(r"[a-z0-9]+(?:[_-][a-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    """Keep identifiers whole and also index their parts.

    ``channel_basket_id`` yields ``channel_basket_id``, ``channel``, ``basket``,
    ``id``; ``OUT-1071`` yields ``out-1071``, ``out``, ``1071``. Exact matches
    on the whole identifier then score higher than matches on its pieces.
    """
    out: list[str] = []
    for tok in _TOKEN.findall(text.lower()):
        out.append(tok)
        parts = re.split(r"[_-]", tok)
        if len(parts) > 1:
            out.extend(p for p in parts if p)
    return out


class BM25Retriever:
    def __init__(self, chunks: list[Document], k1: float = 1.4, b: float = 0.75) -> None:
        self.chunks = chunks
        self.index = BM25Okapi([tokenize(c.page_content) for c in chunks], k1=k1, b=b)

    def search(self, query: str, k: int = 5) -> list[RetrievedChunk]:
        scores = self.index.get_scores(tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:k]
        return [
            to_chunk(self.chunks[i], float(scores[i]), rank)
            for rank, i in enumerate(order, 1)
            if scores[i] > 0
        ]
