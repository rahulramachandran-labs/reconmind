"""Answering without a language model.

Picks the sentences from the retrieved chunks that overlap most with the
question and stitches them together with citations. Used when no LLM is
reachable (CI, the free hosted tier) so the retrieval path still works end to
end. It is honest about being extractive in the answer it returns.
"""

import re

from app.retrieval.types import RetrievedChunk

_WORD = re.compile(r"[a-z0-9_]+")
_STOP = frozenset(
    (
        "a an and are as at be by can do does for from has have how i if in is it of on or our "
        "should the their there this to was we were what when where which who why with you your"
    ).split()
)


def _terms(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1}


def _sentences(text: str) -> list[str]:
    body = text.split("\n", 1)[1] if "\n" in text else text
    out = []
    for part in re.split(r"(?<=[.!?])\s+|\n+", body):
        part = part.replace("**", "").strip(" -|*")
        if part.count("`") % 2:
            part = part.replace("`", "")
        if len(part) > 25 and not part.startswith("---"):
            out.append(part)
    return out


def extractive_answer(question: str, chunks: list[RetrievedChunk], max_sentences: int = 4) -> str:
    if not chunks:
        return "I couldn't find anything in the runbooks or incident history about that."
    q = _terms(question)
    scored: list[tuple[float, int, str]] = []
    for idx, chunk in enumerate(chunks):
        rank_weight = 1.0 / (1 + idx * 0.35)
        for sent in _sentences(chunk.text):
            overlap = len(q & _terms(sent))
            if overlap:
                scored.append((overlap * rank_weight, idx, sent))
    if not scored:
        top = chunks[0]
        return f"Closest match is {top.title} ({top.section}) [1]."
    scored.sort(key=lambda s: (-s[0], s[1]))
    picked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for _, idx, sent in scored:
        if sent not in seen:
            picked.append((idx, sent))
            seen.add(sent)
        if len(picked) == max_sentences:
            break
    lines = [f"- {sent.rstrip('.')}. [{idx + 1}]" for idx, sent in picked]
    return (
        "From the runbooks and past incidents (extractive answer, no LLM configured):\n"
        + "\n".join(lines)
    )
