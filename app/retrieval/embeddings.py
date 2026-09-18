import hashlib
import re
from typing import Any

import numpy as np
from langchain_core.embeddings import Embeddings

_TOKEN = re.compile(r"[a-z0-9_]+")


class SentenceTransformerEmbeddings(Embeddings):
    """Local embeddings, no API calls. The model is loaded lazily on first use."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vecs = self._load().encode(texts, batch_size=32, normalize_embeddings=True)
        return [list(map(float, v)) for v in vecs]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class FastEmbedEmbeddings(Embeddings):
    """The same MiniLM weights run through onnxruntime. Used in the hosted image,
    where torch alone would take most of a 512 MB instance."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(self.model_name)
        return self._model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._load().embed(texts, batch_size=32)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class OpenAIEmbeddings(Embeddings):
    def __init__(self, model_name: str, client: Any) -> None:
        self.model_name = model_name
        self.client = client

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 256):
            resp = self.client.embeddings.create(model=self.model_name, input=texts[i : i + 256])
            out.extend(d.embedding for d in resp.data)
        return out

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class HashingEmbeddings(Embeddings):
    """Deterministic bag-of-words vectors via feature hashing.

    Only meant for tests and environments where the model can't be downloaded.
    It is a weak retriever on purpose; nothing should be tuned against it.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _embed(self, text: str) -> list[float]:
        v = np.zeros(self.dim, dtype=np.float32)
        for tok in _TOKEN.findall(text.lower()):
            h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
            v[h % self.dim] += 1.0 if (h >> 32) & 1 else -1.0
        n = float(np.linalg.norm(v))
        return (v / n if n else v).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def build_embeddings(backend: str, model_name: str, openai_client: Any = None) -> Embeddings:
    if backend == "hashing":
        return HashingEmbeddings()
    if backend == "fastembed":
        return FastEmbedEmbeddings(model_name)
    if backend == "openai":
        if openai_client is None:
            raise ValueError("EMBEDDINGS_BACKEND=openai needs OPENAI_API_KEY")
        return OpenAIEmbeddings(model_name, openai_client)
    return SentenceTransformerEmbeddings(model_name)
