---
title: Duplicate submissions and the latest-file-wins rule
type: runbook
tags: [reconciliation, dedup, submitter_file_name]
---

# Duplicate submissions and the latest-file-wins rule

Submitters resend files. Sometimes it is a correction, sometimes an operator re-ran an export by mistake. Either way the same transaction lands twice and naive totals double count.

## The dedup key

A transaction line is uniquely identified by the composite key:

- `transaction_id`
- `channel_basket_id`
- `upc_code`

`transaction_id` alone is not enough. A basket can hold several UPCs under the same transaction id, and two channels can reuse transaction id ranges.

## Which copy wins

The row from the **latest submitter file** wins. The file timestamp comes from the file name, not from load time, because files are sometimes loaded out of order during catch-up runs:

```
SUBMITTERID_YYYYMMDD_HHMM_NAME.txt
S1002_20260612_1120_ECOMM.txt   <- wins over
S1002_20260612_0305_ECOMM.txt
```

Parse `YYYYMMDD_HHMM` and order by it descending. If two files share the same timestamp (it has happened once), fall back to the lexically greater file name and raise it as an open question in the write-up.

## Detection

```sql
with ranked as (
  select t.*,
         row_number() over (
           partition by transaction_id, channel_basket_id, upc_code
           order by split_part(submitter_file_name, '_', 2) || split_part(submitter_file_name, '_', 3) desc,
                    submitter_file_name desc
         ) as rn
  from transactions t
)
select submitter_file_name, count(*) as superseded_rows
from ranked
where rn > 1
group by 1
order by 2 desc;
```

Rows with `rn > 1` are superseded. Report both the number of duplicate keys and the number of superseded rows; they differ when a key appears in three files.

## Things to check

- Did the resend change `qty` or `amount`? If yes, it is a correction, and the older numbers must not be used anywhere. Say how many rows changed value.
- Is the whole file duplicated or only part of it? A partial overlap usually means the first file was truncated.
- Has the dedupe step in the DAG (`dedupe_transactions`) run since the resend landed?

## Severity

Superseded rows that have reached `fct_daily_sales` are S2 (reported revenue is overstated). If dedup caught them before publish it is S3 and mostly a submitter-hygiene conversation.
