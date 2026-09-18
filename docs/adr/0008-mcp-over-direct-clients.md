# 0008. Agents reach the pipeline through MCP, not direct clients

- Status: accepted
- Date: 2026-09-18

## Context

The specialists need warehouse metadata (schemas, the dbt manifest, table stats) and orchestrator metadata (runs, task logs, timings). The shortcut is to hand them a database session and a file path. That couples the agents to one warehouse and one orchestrator, and it gives them far more access than they need.

## Decision

Two MCP servers, one per system:

- `warehouse-metadata`: `list_tables`, `get_table_schema`, `get_dbt_manifest`, `get_table_stats`, `run_check`.
- `orchestration-metadata`: `list_dag_runs`, `get_task_log`, `get_timing_history`, `get_failed_tasks`.

Rules for both:

- Read-only. Queries run in a read-only transaction, no tool accepts SQL, and table names come from an allow-list. Reconciliation logic is exposed as named checks (`run_check("duplicate_keys", ...)`), not as a query tool.
- Every argument is validated by the tool's Pydantic signature (literals, date patterns, id patterns) before any code runs.
- Transports: stdio subprocesses by default (local runs and the single-container deploy), streamable HTTP in Docker Compose, in-process in tests. The agents don't know which.

## Consequences

- Pointing ReconMind at another warehouse means writing another server with the same tools; the agents and the adapter's interpretation of the results stay put.
- Every tool call goes through one client (`MCPToolBox`), which makes it a single place to trace, time and fail cleanly.
- stdio servers cost a subprocess each. That is irrelevant at this scale, and HTTP is one environment variable away.
