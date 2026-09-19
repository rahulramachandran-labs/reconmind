"""The retail business rules as data: keys, thresholds and the tool servers the
checks read from. Changing a threshold here changes it everywhere."""

from datetime import datetime
from typing import Any

WAREHOUSE = "warehouse-metadata"
ORCHESTRATION = "orchestration-metadata"
DAG_ID = "retail_txn_daily"

# a row is unique on these; a resend repeats them and the latest file wins
DEDUP_KEY = ("transaction_id", "channel_basket_id", "upc_code")
# every outlet_id should map to exactly one location_id
KEY_DRIFT_PAIR = ("outlet_id", "location_id")
KEY_DRIFT_S2_RATE = 0.02

# words in a past incident's title that make it a precedent for a finding type; an
# unrelated incident that happens to be retrieved is not cited
PRECEDENT_WORDS = {
    "key_drift": ("outlet id", "two outlet"),
    "duplicate_submission": ("resend", "double"),
    "schema_drift": ("renamed", "column"),
    "volume_anomaly": ("truncated", "light", "volume"),
}

VOLUME_WINDOW_DAYS = 7
VOLUME_DROP = 0.25
VOLUME_DROP_S1 = 0.50
VOLUME_SPIKE = 0.60
MIN_HISTORY_DAYS = 3


def file_timestamp(name: str) -> str:
    """``S1002_20260612_1120_ECOMM.txt`` -> ``20260612_1120``; the latest file wins."""
    parts = name.split("_")
    return f"{parts[1]}_{parts[2]}" if len(parts) >= 3 else name


def latest_file_per_submitter(files: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """For one business day, keep each submitter's most recent file."""
    latest: dict[str, dict[str, Any]] = {}
    for f in files:
        cur = latest.get(f["submitter_id"])
        if cur is None or file_timestamp(f["file_name"]) > file_timestamp(cur["file_name"]):
            latest[f["submitter_id"]] = f
    return latest


def name_similarity(a: str, b: str) -> float:
    """Share of snake_case words two column names have in common."""
    ta, tb = set(a.lower().split("_")), set(b.lower().split("_"))
    return len(ta & tb) / max(len(ta | tb), 1)


def minutes_between(a: str, b: str) -> int:
    return int((datetime.fromisoformat(a) - datetime.fromisoformat(b)).total_seconds() // 60)
