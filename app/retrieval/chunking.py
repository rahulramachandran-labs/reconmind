from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from app.retrieval.corpus import SourceDoc

HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]


def chunk_docs(
    docs: list[SourceDoc], chunk_size: int = 900, chunk_overlap: int = 120
) -> list[Document]:
    """Split by markdown section first, then by size.

    Each chunk is prefixed with its title and section path so a chunk that only
    says "Fix" still carries what it is fixing.
    """
    by_header = MarkdownHeaderTextSplitter(HEADERS, strip_headers=True)
    by_size = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunks: list[Document] = []
    for doc in docs:
        sections = by_header.split_text(doc.body) or [Document(page_content=doc.body)]
        for section in sections:
            # h1 is the document title, so the section path starts at h2
            path = [section.metadata[h] for h in ("h2", "h3") if h in section.metadata]
            section_name = " > ".join(path) or "Overview"
            for i, piece in enumerate(by_size.split_text(section.page_content)):
                chunks.append(
                    Document(
                        page_content=f"{doc.title} | {section_name}\n{piece}",
                        metadata={
                            "chunk_id": f"{doc.doc_id}#{_slug(section_name)}-{i}",
                            "doc_id": doc.doc_id,
                            "path": doc.path,
                            "title": doc.title,
                            "doc_type": doc.doc_type,
                            "section": section_name,
                        },
                    )
                )
    return chunks


def _slug(text: str) -> str:
    return "-".join("".join(c.lower() if c.isalnum() else " " for c in text).split())
