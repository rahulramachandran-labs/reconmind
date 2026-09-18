import re
from functools import lru_cache

import snowballstemmer
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from app.retrieval.dense import to_chunk
from app.retrieval.types import RetrievedChunk

_TOKEN = re.compile(r"[a-z0-9]+(?:[_-][a-z0-9]+)*")
_STEMMER = snowballstemmer.stemmer("english")


@lru_cache(maxsize=50_000)
def _stem(word: str) -> str:
    return str(_STEMMER.stemWord(word))


def tokenize(text: str) -> list[str]:
    """Keep identifiers whole and also index their stemmed parts.

    ``channel_basket_id`` yields ``channel_basket_id``, ``channel``, ``basket``,
    ``id``; ``OUT-1071`` yields ``out-1071``, ``out``, ``1071``. Exact matches
    on the whole identifier then score higher than matches on its pieces.
    Plain words are stemmed so "caused" meets "cause" and "detect" meets
    "detection".
    """
    out: list[str] = []
    for tok in _TOKEN.findall(text.lower()):
        parts = [p for p in re.split(r"[_-]", tok) if p]
        if len(parts) > 1:
            out.append(tok)
            out.extend(_stem(p) for p in parts)
        else:
            out.append(_stem(tok))
    return out


class BM25Retriever:
    def __init__(self, chunks: list[Document], k1: float = 1.2, b: float = 0.5) -> None:
        # b=0.5: chunks that carry a table are long for good reason, so length is
        # penalised less than the textbook 0.75
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
