---
title: "INC-0438: MOBILE file renamed a dedup-key column"
type: incident
tags: [incident, schema-drift, contract, channel_basket_id]
severity: S1
date: 2026-04-06
---

# INC-0438: MOBILE file renamed a dedup-key column

**Severity:** S1. **Status:** resolved.

## Problem
`validate_schema` failed for 2026-04-05 with:

```
ContractViolation: S1003_20260405_0240_MOBILE.txt missing [channel_basket_id]; unexpected [basket_id]
```

## Affected records
All 9,977 rows from that file were loaded into `transactions` by the previous task with `channel_basket_id` null. Dedup could not run for them.

## Root cause
The mobile team shipped a new export library that renamed `channel_basket_id` to `basket_id`. The value profile was identical (`BSK-` prefix, same length), so it was a rename and not a drop.

## Fix
Submitter resent with the contracted header at 11:05 the same day. The day was reprocessed; the null-key rows were superseded by the resend under latest-file-wins.

## Lessons
Renames of dedup-key columns are S1 even when no data is lost, because dedup silently stops working for that batch. We asked all submitters to run their exports against the published header before releases.
