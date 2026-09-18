---
title: Schema drift against the dbt contract
type: runbook
tags: [data-quality, schema-drift, dbt, contract]
---

# Schema drift against the dbt contract

The contract for raw submitter files is the column list of the `raw_transactions` source in the dbt manifest. Schema drift is any difference between an incoming batch and that contract.

## Tolerance rules

| Change | Tolerated? | Severity if not |
|---|---|---|
| New nullable column appended at the end | Yes, log only | - |
| Column order changed, same names | Yes, loader maps by name | - |
| Column renamed | No | S1 if the column is part of the dedup key, otherwise S2 |
| Column dropped | No | S1 if required or part of the dedup key, otherwise S2 |
| Type widened (int to bigint, numeric precision up) | Yes | - |
| Type narrowed or changed family (numeric to text) | No | S2 |

The dedup key columns are `transaction_id`, `channel_basket_id` and `upc_code`. Losing any of them means dedup cannot run for that batch, which is why it is S1.

## Detecting a rename vs a drop

A rename shows up as one missing column plus one unexpected column in the same batch. Compare names with a normalized similarity (lowercase, strip underscores, compare tokens) and compare the value profile: a renamed `channel_basket_id` will still contain `BSK-` prefixed values. If the profile matches, call it a rename; otherwise report a drop and an unrelated addition.

## Where to look

- The `validate_schema` task in the `retail_txn_daily` DAG fails with `ContractViolation` when a batch breaks the contract. Its log names the file and the offending columns.
- The raw table will show a spike in nulls for the missing column for rows from that file, because the loader maps by name and leaves unknown targets null.

```sql
select submitter_file_name,
       count(*) as rows,
       count(*) filter (where channel_basket_id is null) as null_basket_ids
from transactions
where event_ts::date = :business_date
group by 1
having count(*) filter (where channel_basket_id is null) > 0;
```

## Fix

1. Do not change the contract to match the file. The contract is what downstream models rely on.
2. Ask the submitter to resend with the contracted header.
3. If the business needs the data before the resend, add a one-off mapping in the loader config for that file only, reload, and note it in the audit ledger.
