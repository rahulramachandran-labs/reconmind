---
title: "INC-0463: every submitter late after a credential rotation"
type: incident
tags: [incident, orchestration, sensor, timeout]
severity: S1
date: 2026-05-28
---

# INC-0463: every submitter late after a credential rotation

**Severity:** S1. **Status:** resolved.

## Problem
`wait_for_submitter_files` timed out after 6 hours for 2026-05-27. All downstream tasks were `upstream_failed` and no data was published.

## Affected records
The whole business day, all four submitters. Files had in fact landed on time.

## Root cause
The landing bucket credentials were rotated at 01:30 UTC and the DAG connection still had the old secret. The sensor could not list the bucket and treated that as "file not there yet".

## Fix
Updated the connection, cleared the sensor, and the run completed by 09:20.

## Lessons
All submitters late on the same day is almost never the submitters. The sensor now fails fast on an authorization error instead of poking until timeout.
