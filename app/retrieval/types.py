from pydantic import BaseModel


class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    path: str
    section: str
    doc_type: str
    text: str
    score: float
    rank: int
    dense_rank: int | None = None
    bm25_rank: int | None = None
