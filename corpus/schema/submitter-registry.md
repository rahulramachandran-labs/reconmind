---
title: submitter_registry
type: schema
tags: [schema, reference, submitters]
---

# submitter_registry

| Column | Type | Notes |
|---|---|---|
| submitter_id | text | `S1001`, `S1002`, ... Primary key. |
| submitter_name | text | Short name used in file names, e.g. `POSFEED`. |
| channel | text | `store`, `web`, `app`, `kiosk`. |
| expected_daily_files | integer | Always 1 today. |
| sla_hhmm | text | Latest expected landing time, UTC. |
| contact | text | Team alias to contact for resends. |

POSFEED (S1001) is the largest submitter, a little under half of daily rows. ECOMM (S1002) and MOBILE (S1003) are roughly a fifth each, KIOSK (S1004) the rest.
