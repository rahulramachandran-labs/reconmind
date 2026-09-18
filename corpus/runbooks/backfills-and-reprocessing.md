---
title: Backfills and reprocessing
type: runbook
tags: [operations, backfill, reprocessing]
---

# Backfills and reprocessing

The raw `transactions` table is append-only in spirit and the audit ledger is append-only by enforcement. Fixes never edit raw rows; they change mappings or config and rebuild the models on top.

## Reprocessing a day

1. Land the corrected file (resend) with a later `HHMM` in the file name so latest-file-wins picks it up.
2. Trigger `retail_txn_daily` for the business date with `reprocess=true`. This re-runs dedupe and both dbt models for that date only.
3. Check `publish_metrics` output against the file trailer counts.
4. Write a ledger entry with the incident id, the date range, and who approved it.

## Remapping keys

For key drift, add rows to `outlet_alias` and rebuild `stg_transactions` for the affected range. Backfill in ascending date order so the trailing averages used by volume checks are rebuilt correctly.

## Don'ts

- Don't delete superseded duplicate rows. Dedup handles them and the history is useful evidence.
- Don't reprocess more than 30 days in one run without warning the analytics team; `fct_daily_sales` is rebuilt partition by partition and dashboards will flicker.
