from app.extractive import _sentences, extractive_answer
from app.retrieval.types import RetrievedChunk


def chunk(text: str, i: int = 1) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=f"c{i}",
        doc_id="d",
        title="T",
        path="p.md",
        section="S",
        doc_type="runbook",
        text=text,
        score=1.0,
        rank=i,
    )


def test_picks_sentences_that_match_the_question() -> None:
    chunks = [
        chunk("Dup | Rule\nThe row from the latest submitter file wins. Weather is nice today.", 1),
        chunk("Other | x\nVolume is compared with a trailing seven day average.", 2),
    ]
    out = extractive_answer("which submitter file wins?", chunks)
    assert "latest submitter file wins. [1]" in out
    assert "Weather" not in out
    assert "no LLM configured" in out


def test_no_chunks_says_so() -> None:
    assert "couldn't find" in extractive_answer("anything", [])


def test_no_overlap_points_at_closest_document() -> None:
    out = extractive_answer("zebra", [chunk("T | S\nCompletely unrelated sentence about stores.")])
    assert out.startswith("Closest match is T")


def test_sentence_cleanup_strips_markdown_noise() -> None:
    sents = _sentences(
        "T | S\n**The row from the latest file wins.**\n|---|---|\n`YYYYMMDD_HHMM` decides order`"
    )
    assert "The row from the latest file wins." in sents
    assert all("**" not in s for s in sents)
    assert not any(s.startswith("---") for s in sents)
