from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class SourceDoc:
    doc_id: str
    path: str
    title: str
    doc_type: str
    body: str
    meta: dict[str, Any] = field(default_factory=dict)


def _split_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    meta = yaml.safe_load(text[4:end]) or {}
    return meta, text[end + 5 :]


def load_corpus(root: Path) -> list[SourceDoc]:
    docs = []
    for path in sorted(root.rglob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        meta, body = _split_front_matter(path.read_text(encoding="utf-8"))
        rel = path.relative_to(root).as_posix()
        docs.append(
            SourceDoc(
                doc_id=rel.removesuffix(".md"),
                path=rel,
                title=str(meta.get("title") or path.stem),
                doc_type=str(meta.get("type") or path.parent.name),
                body=body.strip(),
                meta=meta,
            )
        )
    return docs
