---
title: Late or missing submitter files
type: runbook
tags: [orchestration, sla, sensor, timing]
---

# Late or missing submitter files

Each submitter has an SLA for when its daily file should land, listed in `submitter_registry.sla_hhmm` (UTC). The `wait_for_submitter_files` sensor in `retail_txn_daily` pokes every 5 minutes and times out after 6 hours.

## Signals

- Sensor duration well above its trailing median. Normal is under 20 minutes because most files land before the DAG starts.
- File name timestamp (`HHMM` part) later than the submitter SLA.
- A late file that is also small. Late and small together usually means the upstream export was interrupted and someone pushed whatever was there.

## Triage

1. Look up the DAG run for the business date and read the sensor task duration and log.
2. Compare file arrival time against the SLA. Record the lateness in minutes in the write-up.
3. Check the row count against the trailing average (volume-anomalies runbook).
4. If the file never arrived, the sensor fails after 6 hours and downstream tasks are `upstream_failed`. Do not mark the sensor success manually; that publishes an empty day.

## Severity

Late within 2 hours of SLA with a normal row count: S3. Late with a volume drop: take the volume severity. Missing entirely past the timeout: S1.
