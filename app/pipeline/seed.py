"""Load the committed sample into DATABASE_URL if it isn't there yet.

python -m app.pipeline.seed
"""

from app.config import ROOT
from app.db.session import get_engine
from app.pipeline.loader import load_pipeline


def main() -> None:
    stats = load_pipeline(get_engine(), ROOT / "data" / "sample", actor="seed")
    print(f"seed: loaded {stats.files} files / {stats.rows} rows, {stats.skipped} already present")


if __name__ == "__main__":
    main()
