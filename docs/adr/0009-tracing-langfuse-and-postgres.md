# 0009. Trace every step to Postgres, mirror to LangFuse

- Status: accepted
- Date: 2026-09-18

## Context

"Why did it say that?" has to be answerable after the fact, without rerunning anything. LangFuse is the right viewer for LLM traces: prompts, token costs, latency, prompt versions. But it is heavy to self-host, and the app has to work on a free tier and in CI where it isn't running.

## Decision

- A `RunTracer` records every node, LLM call, tool call and retrieval as a step, with provider, model, prompt version, tokens, cost, latency and a preview of input and output.
- Steps always go to the `agent_steps` table. The Traces screen reads from there, so it works on any deployment.
- When `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set, the same steps are mirrored to LangFuse. Nodes become agent observations, and LLM calls become generations nested under them, with usage and cost. The trace id is derived from the run id, and each report links to it.
- `TracedLLM` is the only way agents call a model, and it raises if there is no active run. An LLM call that isn't traced is a crash, not a gap in the data. A test counts provider calls against recorded steps.
- Tracing failures are logged and swallowed. A tracing outage must never fail an investigation.

## Consequences

- Two copies of the trace when LangFuse is on. The Postgres copy is small (previews, not full payloads) and doubles as the data for the Traces screen and the dashboard's cost tiles.
- The Docker Compose stack includes LangFuse v3 (web, worker, ClickHouse, Redis, MinIO) for a full local setup. The hosted demo runs without it and still has complete traces in Postgres.
