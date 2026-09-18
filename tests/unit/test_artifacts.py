import filecmp
import json
from pathlib import Path

from app.config import ROOT
from app.pipeline.artifacts import data_dictionary, write_all
from app.pipeline.synthetic import GeneratorConfig, generate


def test_committed_sample_matches_the_generator(tmp_path: Path) -> None:
    """If this fails, rerun scripts/generate_synthetic_pipeline.py and commit the result."""
    write_all(
        generate(GeneratorConfig()), tmp_path / "sample", tmp_path / "dbt", tmp_path / "DD.md"
    )
    committed = ROOT / "data" / "sample"
    fresh = sorted(
        p.relative_to(tmp_path / "sample") for p in (tmp_path / "sample").rglob("*") if p.is_file()
    )
    assert fresh == sorted(p.relative_to(committed) for p in committed.rglob("*") if p.is_file())
    for rel in fresh:
        assert filecmp.cmp(tmp_path / "sample" / rel, committed / rel, shallow=False), rel
    for rel in ["dbt_project.yml", "models/sources.yml", "target/manifest.json"]:
        assert filecmp.cmp(tmp_path / "dbt" / rel, ROOT / "dbt" / rel, shallow=False), rel
    assert (tmp_path / "DD.md").read_text() == (ROOT / "data" / "DATA_DICTIONARY.md").read_text()


def test_manifest_contract_lists_the_dedup_key(tmp_path: Path) -> None:
    write_all(
        generate(GeneratorConfig(rows_per_day=100)),
        tmp_path / "s",
        tmp_path / "dbt",
        tmp_path / "d.md",
    )
    manifest = json.loads((tmp_path / "dbt" / "target" / "manifest.json").read_text())
    source = manifest["sources"]["source.retail_recon.raw.transactions"]
    assert source["config"]["contract"]["enforced"] is True
    assert {"transaction_id", "channel_basket_id", "upc_code"} <= set(source["columns"])
    assert "model.retail_recon.stg_transactions" in manifest["nodes"]


def test_rewriting_removes_stale_landing_files(tmp_path: Path) -> None:
    out = tmp_path / "s"
    (out / "landing").mkdir(parents=True)
    (out / "landing" / "S9999_20200101_0000_OLD.txt").write_text("x")
    write_all(
        generate(GeneratorConfig(days=2, rows_per_day=40, anomalies=frozenset())),
        out,
        tmp_path / "dbt",
        tmp_path / "d.md",
    )
    assert not (out / "landing" / "S9999_20200101_0000_OLD.txt").exists()
    assert len(list((out / "landing").glob("*.txt"))) == 8


def test_dictionary_documents_every_planted_anomaly() -> None:
    text = data_dictionary(generate(GeneratorConfig(rows_per_day=100)))
    for heading in [
        "### Key drift",
        "### Duplicate submission",
        "### Schema drift",
        "### Volume anomaly",
    ]:
        assert heading in text
    clean = data_dictionary(generate(GeneratorConfig(rows_per_day=100, anomalies=frozenset())))
    assert "### Key drift" not in clean
