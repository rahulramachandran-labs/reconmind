---
title: Key drift between outlet_id and location_id
type: runbook
tags: [reconciliation, key-drift, outlet_id, location_id]
---

# Key drift between outlet_id and location_id

Every physical store has exactly one `location_id` and, at any point in time, exactly one active `outlet_id`. The mapping lives in `outlet_location_map`. Key drift is when a single `location_id` shows up in `transactions` under more than one `outlet_id` for the same business day.

## Why it matters

Downstream models join on `outlet_id`. When a location reports under two outlet ids, its sales split across two rows in `fct_daily_sales`, the "second" outlet looks like a brand new store with no history, and store-level comparisons break. Totals across the whole estate are still correct, which is why this one tends to survive for weeks before anyone notices.

## Common causes

- A submitter hard-codes an outlet id and a digit gets transposed (`OUT-1017` becomes `OUT-1071`).
- A store is re-numbered and the submitter switches over mid-day instead of at midnight.
- A shared POS back office submits for two stores and mixes up the header record.

## Detection

```sql
select location_id,
       count(distinct outlet_id) as outlet_ids,
       array_agg(distinct outlet_id) as seen_outlets,
       count(*) as rows
from transactions
where event_ts::date = :business_date
group by location_id
having count(distinct outlet_id) > 1;
```

Then compare the outlets seen against `outlet_location_map`. The outlet id that is *not* in the map (or is mapped to a different location) is the drifted one. Report the drift rate as drifted rows divided by total rows for the window, not per location.

## Thresholds

- Any drift at all is a finding. Key drift never self-heals.
- Drift above 2% of rows in the scan window is severity S2 because store-level reporting is materially wrong.
- Drift at or below 2% is S3.

## Fix

1. Confirm with the submitter which outlet id is correct. Do not guess from volume alone.
2. Add the drifted id as an alias in `outlet_alias` with `valid_from` / `valid_to` so the staging model can remap it. Never edit rows in `transactions` directly; the raw layer is immutable and the audit ledger will reject it anyway.
3. Rebuild `stg_transactions` and `fct_daily_sales` for the affected dates (see the backfill runbook).
4. Ask the submitter to fix the header at source and record the ticket number in the incident write-up.
