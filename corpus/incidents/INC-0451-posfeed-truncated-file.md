---
title: "INC-0451: POSFEED file truncated in transfer"
type: incident
tags: [incident, volume, truncation, late-file]
severity: S2
date: 2026-05-12
---

# INC-0451: POSFEED file truncated in transfer

**Severity:** S2. **Status:** resolved.

## Problem
Row count for S1001 (POSFEED) on 2026-05-11 was 37% below its trailing 7-day average. The file landed at 06:40 UTC against a 04:00 SLA.

## Affected records
Around 11,300 missing rows, spread evenly across all 40 outlets. No outlet was missing entirely.

## Root cause
The export job on the submitter side hit a disk quota and the transfer agent shipped the partial file once the retry window expired. The trailer record was missing, but at the time `load_raw_transactions` only warned on a missing trailer.

## Fix
Full resend at 10:15, day reprocessed.

## Lessons
A missing trailer is now a hard failure. Even spread across outlets plus a late arrival is the signature of a truncated file; stores being offline shows up concentrated in a few outlets instead.
