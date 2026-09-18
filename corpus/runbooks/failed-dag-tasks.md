---
title: Triage for failed tasks in retail_txn_daily
type: runbook
tags: [orchestration, airflow, dag, task-failure]
---

# Triage for failed tasks in retail_txn_daily

Task order in the DAG:

1. `wait_for_submitter_files` (sensor)
2. `load_raw_transactions`
3. `validate_schema`
4. `dedupe_transactions`
5. `build_stg_transactions`
6. `build_fct_daily_sales`
7. `publish_metrics`

Tasks retry twice with a 10 minute delay. A task that is `failed` has used all its tries.

## By task

**wait_for_submitter_files** fails on timeout. See the late-or-missing-files runbook. After a credential rotation on the landing bucket this sensor will time out for every submitter at once; that pattern (all submitters, same day) points at access, not at the submitters.

**load_raw_transactions** failures are mostly malformed files: wrong delimiter, bad encoding, trailer record count not matching. The log names the file and line.

**validate_schema** fails with `ContractViolation` when a batch does not match the dbt contract. The log lists missing and unexpected columns. This is the task that catches schema drift, so read the schema-drift runbook next. Downstream tasks for that run are `upstream_failed`, but rows already loaded into `transactions` by the previous task stay there.

**dedupe_transactions** rarely fails. When it does it is usually a lock timeout during a concurrent backfill.

**build_*** tasks fail on dbt test failures. `not_null` on `channel_basket_id` and `relationships` between `outlet_id` and `dim_outlet` are the two tests that catch most real problems.

## What to put in the write-up

Task id, try number, the first error line from the log, the file involved, and whether any downstream model was published with partial data.
