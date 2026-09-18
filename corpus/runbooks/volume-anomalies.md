---
title: Volume anomalies
type: runbook
tags: [data-quality, volume, anomaly, trailing-average]
---

# Volume anomalies

A volume anomaly is a day where the row count for a submitter (or the whole feed) moves far away from its recent history.

## Method

- Window: trailing 7 business days, excluding the day being checked.
- Metric: row count per submitter per business day.
- Flag when the day is more than **25% below** the trailing average, or more than 60% above it.
- Drops are more interesting than spikes. A spike is usually a resend (check the duplicate-submissions runbook first).

```sql
with daily as (
  select split_part(submitter_file_name, '_', 1) as submitter_id,
         event_ts::date as d,
         count(*) as rows
  from transactions
  group by 1, 2
)
select d, submitter_id, rows,
       avg(rows) over (partition by submitter_id order by d rows between 7 preceding and 1 preceding) as trailing_avg
from daily
order by d desc;
```

## Severity

- More than 50% below trailing average: S1, treat as possible data loss.
- 25% to 50% below: S2.
- Spike above 60%: S3 until duplicates are ruled out.

## First questions to answer

1. Did the file land on time? Check the `wait_for_submitter_files` sensor duration in the DAG history. A late file often goes with a truncated one.
2. Is the drop spread across all outlets for that submitter, or concentrated in a few? Spread evenly suggests a truncated file; concentrated suggests stores offline.
3. Did `load_raw_transactions` log a row count that matches the file trailer record?
4. Is it a known low day (public holiday, planned store closures)? Check the calendar before paging anyone.

## Fix

Truncated file: request a full resend, then reprocess the day. Stores offline: no fix needed in the pipeline, but annotate the day so the trailing average for next week is not dragged down.
