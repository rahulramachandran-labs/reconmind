from pathlib import Path

from app.core.config import ROOT
from app.retrieval.chunking import chunk_docs
from app.retrieval.corpus import _split_front_matter, load_corpus


def test_front_matter_is_parsed() -> None:
    meta, body = _split_front_matter("---\ntitle: X\ntype: runbook\n---\n# X\nbody")
    assert meta == {"title": "X", "type": "runbook"}
    assert body.startswith("# X")


def test_missing_or_unterminated_front_matter_leaves_text_alone() -> None:
    assert _split_front_matter("# plain") == ({}, "# plain")
    assert _split_front_matter("---\ntitle: X\n# never closed") == (
        {},
        "---\ntitle: X\n# never closed",
    )


def test_load_corpus_reads_every_markdown_file_but_readmes(tmp_path: Path) -> None:
    (tmp_path / "runbooks").mkdir()
    (tmp_path / "runbooks" / "a.md").write_text("---\ntitle: A\ntype: runbook\n---\n# A\ntext")
    (tmp_path / "runbooks" / "b.md").write_text("# no front matter")
    (tmp_path / "README.md").write_text("skip me")
    docs = load_corpus(tmp_path)
    assert [d.doc_id for d in docs] == ["runbooks/a", "runbooks/b"]
    assert docs[1].title == "b"
    assert docs[1].doc_type == "runbooks"


def test_real_corpus_has_every_document_type() -> None:
    types = {d.doc_type for d in load_corpus(ROOT / "corpus")}
    assert {"runbook", "schema", "incident"} <= types


def test_chunks_carry_title_and_section() -> None:
    chunks = chunk_docs(load_corpus(ROOT / "corpus"))
    ids = [c.metadata["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids)), "chunk ids must be unique"
    for c in chunks:
        assert c.page_content.startswith(c.metadata["title"])
        assert len(c.page_content) < 1200


def test_long_sections_are_split_with_overlap(tmp_path: Path) -> None:
    sentence = "The dedup key is transaction_id plus channel_basket_id plus upc_code. "
    (tmp_path / "long.md").write_text("# Long\n## Detail\n" + sentence * 40)
    chunks = chunk_docs(load_corpus(tmp_path), chunk_size=300, chunk_overlap=60)
    assert len(chunks) > 3
    assert all(c.metadata["section"] == "Detail" for c in chunks)
