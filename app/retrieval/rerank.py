"""Cross-encoder reranking over the fused candidates.

On the golden set, reranking the hybrid top 10 lifted context precision from
0.756 to 0.830 (ADR 0002). The same MiniLM MS MARCO model runs on
sentence-transformers locally and on onnxruntime in the container.
"""

import math
from typing import Any, Protocol

from app.retrieval.types import RetrievedChunk


class Reranker(Protocol):
    def rerank(self, query: str, hits: list[RetrievedChunk], k: int) -> list[RetrievedChunk]: ...


class _Base:
    def _scores(self, query: str, texts: list[str]) -> list[float]:
        raise NotImplementedError

    def rerank(self, query: str, hits: list[RetrievedChunk], k: int) -> list[RetrievedChunk]:
        if not hits:
            return hits
        scores = self._scores(query, [h.text for h in hits])
        order = sorted(range(len(hits)), key=lambda i: (-scores[i], hits[i].rank))[:k]
        return [
            hits[i].model_copy(
                update={"score": round(1 / (1 + math.exp(-scores[i])), 4), "rank": n}
            )
            for n, i in enumerate(order, 1)
        ]


class CrossEncoderReranker(_Base):
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: Any = None

    def _scores(self, query: str, texts: list[str]) -> list[float]:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self.model_name, device="cpu")
        return [float(s) for s in self._model.predict([(query, t) for t in texts])]


class FastEmbedReranker(_Base):
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: Any = None

    def _scores(self, query: str, texts: list[str]) -> list[float]:
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._model = TextCrossEncoder(self.model_name)
        return [float(s) for s in self._model.rerank(query, texts)]


def build_reranker(kind: str, embeddings_backend: str, model_name: str) -> Reranker | None:
    if kind == "none":
        return None
    if embeddings_backend == "fastembed":
        # fastembed publishes the same weights under the Xenova namespace
        return FastEmbedReranker(model_name.replace("cross-encoder/", "Xenova/"))
    return CrossEncoderReranker(model_name)
