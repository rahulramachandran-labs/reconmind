from collections import Counter, defaultdict
from datetime import date

import pytest

from app.pipeline.synthetic import (
    ALL_ANOMALIES,
    CONTRACT_COLUMNS,
    DUPLICATES,
    KEY_DRIFT,
    SCHEMA_DRIFT,
    VOLUME,
    GeneratorConfig,
    SyntheticPipeline,
    generate,
    parse_file_name,
)

SMALL = GeneratorConfig(days=21, rows_per_day=200)


@pytest.fixture(scope="module")
def pipeline() -> SyntheticPipeline:
    return generate(SMALL)


def test_same_seed_same_output() -> None:
    a, b = generate(SMALL), generate(SMALL)
    assert [f.render() for f in a.files] == [f.render() for f in b.files]
    assert a.dag_runs == b.dag_runs
    assert a.expected == b.expected


def test_different_seed_different_output() -> None:
    a, b = generate(SMALL), generate(GeneratorConfig(seed=7, rows_per_day=200))
    assert a.files[0].render() != b.files[0].render()


def test_file_names_follow_convention(pipeline: SyntheticPipeline) -> None:
    for f in pipeline.files:
        sid, bdate, hhmm, name = parse_file_name(f.name)
        assert sid == f.submitter_id and bdate == f.business_date
        assert len(hhmm) == 4 and name.isupper()


def test_upc_codes_have_valid_check_digits(pipeline: SyntheticPipeline) -> None:
    for row in pipeline.files[0].rows:
        digits = list(map(int, row[3]))
        assert (sum(digits[0:11:2]) * 3 + sum(digits[1:11:2]) + digits[11]) % 10 == 0


def test_dedup_key_is_unique_within_each_file(pipeline: SyntheticPipeline) -> None:
    for f in pipeline.files:
        idx = [f.header.index(c) for c in ("transaction_id", "upc_code")]
        basket = f.header.index(
            "channel_basket_id" if "channel_basket_id" in f.header else "basket_ref"
        )
        keys = [(r[idx[0]], r[basket], r[idx[1]]) for r in f.rows]
        assert len(keys) == len(set(keys)), f.name


def test_key_drift_count_matches_data(pipeline: SyntheticPipeline) -> None:
    exp = pipeline.expected[KEY_DRIFT]
    resend = pipeline.expected[DUPLICATES]["resend_file"]
    drifted = sum(
        1
        for f in pipeline.files
        if f.name != resend
        for r in f.rows
        if r[0] == exp["drifted_outlet_id"]
    )
    assert drifted == exp["drifted_rows"]
    assert 0.02 < exp["drift_rate"] < 0.045
    assert exp["expected_severity"] == "S2"
    # every drifted row still carries the right location
    assert all(
        r[1] == exp["location_id"]
        for f in pipeline.files
        for r in f.rows
        if r[0] == exp["drifted_outlet_id"]
    )


def test_resend_duplicates_every_key_and_changes_a_few(pipeline: SyntheticPipeline) -> None:
    exp = pipeline.expected[DUPLICATES]
    files = {f.name: f for f in pipeline.files}
    orig, resend = files[exp["original_file"]], files[exp["resend_file"]]
    assert parse_file_name(resend.name)[2] > parse_file_name(orig.name)[2]
    key = lambda r: (r[2], r[4], r[3])  # noqa: E731
    assert {key(r) for r in orig.rows} == {key(r) for r in resend.rows}
    changed = sum(1 for a, b in zip(orig.rows, resend.rows, strict=True) if a != b)
    assert changed == exp["changed_rows"] > 0
    assert exp["duplicate_keys"] == len(orig.rows)


def test_schema_drift_renames_one_column_in_one_file(pipeline: SyntheticPipeline) -> None:
    exp = pipeline.expected[SCHEMA_DRIFT]
    drifted = [f for f in pipeline.files if f.header != CONTRACT_COLUMNS]
    assert [f.name for f in drifted] == [exp["file"]]
    assert "basket_ref" in drifted[0].header
    run = next(r for r in pipeline.dag_runs if r["business_date"] == exp["business_date"])
    states = {t["task_id"]: t["state"] for t in run["tasks"]}
    assert states["validate_schema"] == "failed"
    assert states["publish_metrics"] == "upstream_failed"
    assert run["state"] == "failed"
    assert [r for r in pipeline.dag_runs if r["state"] == "failed"] == [run]


def test_volume_day_is_forty_percent_light_and_late(pipeline: SyntheticPipeline) -> None:
    exp = pipeline.expected[VOLUME]
    counts: dict[str, list[int]] = defaultdict(list)
    for f in pipeline.files:
        if f.submitter_id == exp["submitter_id"]:
            counts[f.business_date.isoformat()].append(len(f.rows))
    days = sorted(counts)
    i = days.index(exp["business_date"])
    trailing = sum(counts[d][0] for d in days[i - 7 : i]) / 7
    assert counts[exp["business_date"]][0] == exp["rows"]
    assert exp["pct_below_trailing"] == pytest.approx(1 - exp["rows"] / trailing, abs=0.002)
    assert 0.35 < exp["pct_below_trailing"] < 0.45
    assert exp["minutes_after_sla"] > 60
    run = next(r for r in pipeline.dag_runs if r["business_date"] == exp["business_date"])
    others = [r["tasks"][0]["duration_s"] for r in pipeline.dag_runs if r is not run]
    assert run["tasks"][0]["duration_s"] > 10 * max(others)


def test_clean_run_plants_nothing() -> None:
    clean = generate(GeneratorConfig(rows_per_day=150, anomalies=frozenset()))
    assert set(clean.expected) == {"summary"}
    assert all(f.header == CONTRACT_COLUMNS for f in clean.files)
    assert all(r["state"] == "success" for r in clean.dag_runs)
    assert len(clean.files) == 21 * 4
    assert not any(r[0] == "OUT-1071" for f in clean.files for r in f.rows)


@pytest.mark.parametrize("only", sorted(ALL_ANOMALIES))
def test_each_anomaly_can_be_planted_alone(only: str) -> None:
    p = generate(GeneratorConfig(rows_per_day=150, anomalies=frozenset({only})))
    assert set(p.expected) == {"summary", only}


def test_submitter_mix_roughly_matches_shares(pipeline: SyntheticPipeline) -> None:
    rows = Counter()
    for f in pipeline.files:
        rows[f.submitter_id] += len(f.rows)
    total = sum(rows.values())
    assert 0.40 < rows["S1001"] / total < 0.50
    assert pipeline.config.business_date(0) == date(2026, 6, 1)
