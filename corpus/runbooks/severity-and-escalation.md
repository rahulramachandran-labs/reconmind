---
title: Finding severity rubric and escalation
type: runbook
tags: [severity, escalation, incident]
---

# Finding severity rubric and escalation

| Severity | Meaning | Examples | Response |
|---|---|---|---|
| S1 | Data loss or a broken contract on a published model | Dedup-key column dropped or renamed; volume more than 50% below trailing average; file missing past sensor timeout | Page the on-call data engineer, hold `publish_metrics` |
| S2 | Published numbers are materially wrong | Superseded duplicates reached `fct_daily_sales`; key drift above 2% of rows; volume 25-50% below trailing average | Fix within the business day, notify analytics |
| S3 | Localized or caught-before-publish | Key drift at or below 2%; duplicates caught by dedupe; late file within 2 hours of SLA | Fix within the week |
| S4 | Cosmetic or informational | New nullable column appended | Log it |

When one incident has several findings, the incident takes the highest severity among them.

## Writing it up

Every incident write-up has: problem statement, affected record counts, root-cause hypothesis, recommended fix, confidence, open questions, and links to the evidence (queries, DAG run ids, retrieved runbooks). A write-up without counts is not finished.

Confidence is about the root cause, not the detection. A detected duplicate is certain; *why* the submitter resent is usually a hypothesis until they confirm.
