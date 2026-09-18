---
title: audit_ledger
type: schema
tags: [schema, audit, ledger, append-only]
---

# audit_ledger

Append-only record of everything that changes how data is interpreted: aliases added, reprocessing runs, manual approvals, agent findings and human review decisions.

| Column | Type | Notes |
|---|---|---|
| id | bigserial | |
| occurred_at | timestamptz | Defaults to now(). |
| actor | text | A person, a service, or an agent name. |
| action | text | e.g. `finding.created`, `review.approved`, `alias.added`, `reprocess.started`. |
| subject | text | What it is about, e.g. an incident id or a table. |
| payload | jsonb | Details. |

A trigger rejects every `UPDATE` and `DELETE` on this table. If something in the ledger is wrong, append a correcting entry that references the original id.
