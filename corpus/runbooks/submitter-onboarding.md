---
title: Submitter files and naming convention
type: runbook
tags: [submitters, file-naming, ingestion]
---

# Submitter files and naming convention

Every submitter drops one pipe-delimited file per business day into the landing area. File names follow:

```
SUBMITTERID_YYYYMMDD_HHMM_NAME.txt
```

- `SUBMITTERID` is the id from `submitter_registry`, for example `S1001`.
- `YYYYMMDD` is the business date the file covers.
- `HHMM` is when the submitter produced the file, in UTC, on the morning after the business date. Together `YYYYMMDD_HHMM` decides which copy wins during dedup.
- `NAME` is the short submitter name, for example `POSFEED`.

Current submitters:

| submitter_id | name | channel | SLA (UTC) |
|---|---|---|---|
| S1001 | POSFEED | store point of sale | 04:00 |
| S1002 | ECOMM | web orders | 03:30 |
| S1003 | MOBILE | mobile app | 03:30 |
| S1004 | KIOSK | self-service kiosks | 05:00 |

## Header

The header must match the contract exactly:

```
outlet_id|location_id|transaction_id|upc_code|channel_basket_id|qty|amount|event_ts
```

The loader adds `submitter_file_name` itself. The last line is a trailer `TRAILER|<row_count>`.

## Resends

A resend uses the same date and a later `HHMM`. Submitters must not reuse a file name; the loader rejects a name it has already seen.
