---
title: retail_txn_daily DAG
type: schema
tags: [orchestration, airflow, dag]
---

# retail_txn_daily DAG

Runs once per business date at 02:00 UTC. Owner: data-platform.

```
wait_for_submitter_files -> load_raw_transactions -> validate_schema
  -> dedupe_transactions -> build_stg_transactions -> build_fct_daily_sales -> publish_metrics
```

| Task | Typical duration | Retries | Notes |
|---|---|---|---|
| wait_for_submitter_files | 5-20 min | 0 | Poke every 5 min, timeout 6 h. |
| load_raw_transactions | 3-6 min | 2 | Checks trailer row count. |
| validate_schema | < 1 min | 0 | Compares each batch header with the dbt contract. |
| dedupe_transactions | 2-4 min | 2 | Applies latest-file-wins on the dedup key. |
| build_stg_transactions | 4-8 min | 2 | dbt model, applies outlet_alias. |
| build_fct_daily_sales | 3-6 min | 2 | dbt model, grain: business date x outlet. |
| publish_metrics | < 1 min | 1 | Writes row counts and totals per submitter. |

Run history (state, start, end, per-task durations and logs) is exposed read-only through the orchestration metadata service.
