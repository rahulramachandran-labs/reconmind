---
title: "INC-0412: store sales split across two outlet ids"
type: incident
tags: [incident, key-drift, outlet_id]
severity: S2
date: 2026-02-09
---

# INC-0412: store sales split across two outlet ids

**Severity:** S2. **Status:** resolved.

## Problem
From 2026-02-02 analytics saw a new outlet `OUT-1290` in `fct_daily_sales` with no history and no entry in `dim_outlet`. Over the same days `OUT-1029` (LOC-0529) dropped by roughly a third.

## Affected records
4,812 rows over 8 business days, 2.6% of all rows in the window. All from submitter S1001 (POSFEED), all for location `LOC-0529`.

## Root cause
The store's back office had been re-imaged and the outlet id in the export profile was typed in by hand as `1290` instead of `1029`. About one in three registers picked up the new profile, so the store reported under both ids at once.

## Fix
Added `OUT-1290 -> OUT-1029` to `outlet_alias` for 2026-02-02 to 2026-02-10, rebuilt staging and facts for those dates, and the store corrected the profile on 2026-02-10.

## Lessons
The relationships test on `stg_transactions.outlet_id` was warn-only. It is now an error. The detection query in the key-drift runbook would have caught it on day one; it now runs in the daily scan.
