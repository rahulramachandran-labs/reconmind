"""Generate the synthetic retail pipeline.

Defaults: seed 42, writes data/sample, dbt/ and data/DATA_DICTIONARY.md.

  uv run python scripts/generate_synthetic_pipeline.py
  uv run python scripts/generate_synthetic_pipeline.py --load
  uv run python scripts/generate_synthetic_pipeline.py --seed 7 --out /tmp/p --only key_drift
"""

import argparse
from datetime import date
from pathlib import Path

from app.core.config import ROOT
from app.pipeline.artifacts import write_all
from app.pipeline.synthetic import ALL_ANOMALIES, GeneratorConfig, generate


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--start", type=date.fromisoformat, default=date(2026, 6, 1))
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--rows-per-day", type=int, default=400)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "sample")
    ap.add_argument("--dbt-dir", type=Path, default=ROOT / "dbt")
    ap.add_argument("--dictionary", type=Path, default=ROOT / "data" / "DATA_DICTIONARY.md")
    ap.add_argument(
        "--only",
        default=",".join(sorted(ALL_ANOMALIES)),
        help="comma separated anomalies to plant (default: all). Use 'none' for a clean run.",
    )
    ap.add_argument("--load", action="store_true", help="load the result into DATABASE_URL")
    args = ap.parse_args()

    anomalies = frozenset() if args.only == "none" else frozenset(args.only.split(","))
    unknown = anomalies - ALL_ANOMALIES
    if unknown:
        ap.error(f"unknown anomalies: {', '.join(sorted(unknown))}")

    cfg = GeneratorConfig(
        seed=args.seed,
        start=args.start,
        days=args.days,
        rows_per_day=args.rows_per_day,
        anomalies=anomalies,
    )
    pipeline = generate(cfg)
    write_all(pipeline, args.out, args.dbt_dir, args.dictionary)
    print(f"{len(pipeline.files)} files, {pipeline.total_rows} rows -> {args.out}")

    if args.load:
        from app.db.session import get_engine
        from app.pipeline.loader import load_pipeline

        stats = load_pipeline(get_engine(), args.out)
        print(f"loaded {stats.rows} rows from {stats.files} files")


if __name__ == "__main__":
    main()
