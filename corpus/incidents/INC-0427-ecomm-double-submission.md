---
title: "INC-0427: ECOMM resend double counted web revenue"
type: incident
tags: [incident, duplicates, dedup, submitter_file_name]
severity: S2
date: 2026-03-17
---

# INC-0427: ECOMM resend double counted web revenue

**Severity:** S2. **Status:** resolved.

## Problem
Web revenue for 2026-03-16 was 1.9x the trailing average in the morning dashboard.

## Affected records
S1002 (ECOMM) sent `S1002_20260316_0310_ECOMM.txt` and then `S1002_20260316_0955_ECOMM.txt`. 6,140 dedup keys appeared in both; 212 of them had a different `qty` or `amount` in the later file (price corrections). All 6,140 older rows are superseded.

## Root cause
The resend landed after `dedupe_transactions` had already run, and the manual reprocess only rebuilt `fct_daily_sales`, skipping dedupe. The later file was a legitimate correction; the process gap was on our side.

## Fix
Reprocessed 2026-03-16 with `reprocess=true` so dedupe ran again. Latest file won for all 6,140 keys.

## Lessons
Reprocessing now always starts from `dedupe_transactions`. When a resend changes values, the write-up must say how many rows changed, because finance cares about that number more than the duplicate count.
