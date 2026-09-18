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


def _tests(tests: list[Any]) -> str:
    out = []
    for t in tests or []:
        if isinstance(t, str):
            out.append(t)
        elif isinstance(t, dict):
            for name, args in t.items():
                out.append(f"{name} {args}" if args else name)
    return ", ".join(out)


def _render_columns(columns: list[dict[str, Any]]) -> list[str]:
    lines = ["| Column | Type | Tests | Description |", "|---|---|---|---|"]
    for c in columns:
        lines.append(
            f"| {c['name']} | {c.get('data_type', '')} | {_tests(c.get('tests', []))} "
            f"| {c.get('description', '')} |"
        )
    return lines


def load_dbt_models(models_dir: Path, prefix: str = "dbt/models") -> list[SourceDoc]:
    """Render dbt schema YAML as markdown so it chunks and reads like the other docs."""
    docs: list[SourceDoc] = []
    if not models_dir.exists():
        return docs
    for path in sorted(models_dir.rglob("*.yml")):
        spec = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rel = f"{prefix}/{path.relative_to(models_dir).as_posix()}"
        for model in spec.get("models", []):
            lines = [f"# dbt model {model['name']}", "", model.get("description", ""), ""]
            lines += ["## Columns", "", *_render_columns(model.get("columns", []))]
            if model.get("tests"):
                lines += ["", "## Model tests", "", _tests(model["tests"])]
            docs.append(
                SourceDoc(
                    doc_id=f"dbt/{model['name']}",
                    path=rel,
                    title=f"dbt model {model['name']}",
                    doc_type="dbt_model",
                    body="\n".join(lines),
                )
            )
        for source in spec.get("sources", []):
            for table in source.get("tables", []):
                name = f"{source['name']}.{table['name']}"
                contract = table.get("config", {}).get("contract", {}).get("enforced")
                lines = [
                    f"# dbt source {name}",
                    "",
                    table.get("description", ""),
                    "",
                    f"Contract enforced: {'yes' if contract else 'no'}.",
                    "",
                    "## Columns",
                    "",
                    *_render_columns(table.get("columns", [])),
                ]
                docs.append(
                    SourceDoc(
                        doc_id=f"dbt/source.{name}",
                        path=rel,
                        title=f"dbt source {name}",
                        doc_type="dbt_model",
                        body="\n".join(lines),
                    )
                )
    return docs
