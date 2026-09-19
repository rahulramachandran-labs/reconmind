# 0011. Scheduled scans from outside the API; findings are fingerprinted

- Status: accepted
- Date: 2026-09-19

## Context

Scans were scheduled with APScheduler inside the API every six hours. On Render's free tier that almost never happens: the instance sleeps after 15 minutes without traffic, and the timer starts again from zero when it wakes.

Making scans actually run on a schedule exposed a second problem. Every scan wrote every finding up again, so the same S1 would land in the review queue four times a day and the incident feed would fill with copies.

## Decision

- **Scheduling moves outside the API.** `.github/workflows/scheduled-scan.yml` runs every six hours: it wakes the API, calls `POST /scan` with the write token (stored as a repository secret), waits for the run and writes the summary to the job page. `SCAN_INTERVAL_MINUTES` stays for always-on deployments and is `0` on Render.
- **Findings are fingerprinted** by type plus title. Titles already carry the subject and the size, so "LOC-0517 also reporting as OUT-1071 (3.0% of rows)" is the same finding until the numbers change. A scan that sees an existing finding increments `seen_count`, updates `last_seen_at` and writes `finding.seen_again` to the ledger, instead of adding a report.
- **A repeat never pauses a run.** If the finding is still waiting for review, it is already in the queue under the run that first reported it. If a reviewer rejected it, it stays rejected.
- **"Open findings" on the dashboard means what the latest scan saw,** minus anything rejected.

## Consequences

- The review queue holds one item per real problem, however often scans run.
- A finding whose numbers change (drift grows from 3.0% to 3.4%) gets a new title, so it becomes a new report that needs a fresh look. That is deliberate: a changing problem deserves a fresh look.
- GitHub disables scheduled workflows in public repositories after 60 days without commits, and can delay scheduled runs at busy times. Both are fine for a demo; a production deployment would use an always-on instance or a platform cron.

## Update, 1.2

The workflow is now `refresh-demo.yml`. After the scan it asks the API's model to write up any finding that has no model write-up yet. Reports duplicated before fingerprints existed are folded into one per finding by migration 0004.
