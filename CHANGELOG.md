# Changelog

All notable changes, grouped by build phase. Dates are UTC.

## [Unreleased]

## [1.1.0] - 2026-09-19

### Added
- Scheduled scans from GitHub Actions (`scheduled-scan.yml`, every six hours and on demand): wakes the API, starts a scan with the write token from a repository secret, and writes the run summary to the job page.
- Findings are fingerprinted. A scan that sees a finding an earlier scan reported increments its `seen_count` and `last_seen_at` and writes `finding.seen_again` to the ledger instead of creating a new report. Repeats never pause a run, and rejected findings stay rejected. Migration 0003 backfills fingerprints.
- The incident feed shows how many scans have seen each finding.
- ADR 0011.
- `keep-warm.yml` pings `/healthz` every ten minutes from 03:00 to 19:00 UTC so the free instance doesn't sleep while people are looking at the demo. It stops after `KEEP_WARM_UNTIL` (a repository variable, default 2026-10-05), because free instance hours are shared across the Render workspace.

### Changed
- Dashboard "open findings" counts what the latest scan saw, minus rejected ones.
- Render runs with `SCAN_INTERVAL_MINUTES=0`; a free instance sleeps too often for an in-process timer.
- `docs/DEMO.md` gives the free-tier scan time (about fifteen seconds, against four locally) and says what to show if someone has already cleared the review queue.

### Fixed
- The package, the API and the web app all report 1.1.0; `/healthz` still said 0.1.0.

## [1.0.1] - 2026-09-18

### Fixed
- `make dev` starts Postgres, applies migrations and loads the sample itself, so `make bootstrap && make dev` works from a clean clone.
- `make bootstrap` writes `frontend/.env.local` with a fresh `AUTH_SECRET`; without it Auth.js refused to sign anyone in locally.
- MinIO for the LangFuse stack now comes from quay.io; the Docker Hub image is gone.

### Changed
- Demo GIF re-recorded with the final dashboard.
- Checked the LangFuse mirror against a real self-hosted LangFuse 3: every node, tool call, retrieval and generation from a run arrives with prompt version and token usage, 15 of 15 steps.

## [1.0.0] - 2026-09-18

### Added
- Dashboard: volume for the latest business date against its trailing week, a 14-day chart that flags light days per submitter, open findings by severity, the last pipeline run, and today's model usage and cost.
- Auth.js sign-in: a demo reviewer for the public site and GitHub OAuth with an allow-list. Scans and review decisions go through a server-side route that adds the API's write token and the reviewer's name.
- APScheduler scans inside the API on a configurable interval (six hours on Render).
- Per-client rate limits on chat, ask and scan.
- Cross-encoder reranking over the fused top 10 (context precision 0.756 to 0.830); the offline relevancy judge moved to the 12-layer model.
- Chaos suite: each anomaly planted alone with the generator must be caught by the right agent at the right severity, and a clean pipeline must produce nothing. A full demo-mode scan must finish in under 30 seconds.
- In-process MCP transport for single-container deploys.
- 60-second demo script, blog draft, demo GIF and the Playwright script that records it.

### Changed
- Eval thresholds raised from 0.75 across the board to faithfulness 0.85, answer relevancy 0.80, context precision 0.80, context recall 0.85.
- The dashboard is the landing page; Ask ReconMind moved to `/ask`.

## [phase-c] - 2026-09-18

### Added
- Two read-only MCP servers: `warehouse-metadata` (tables, schema, dbt manifest, per-day stats, named reconciliation checks) and `orchestration-metadata` (DAG runs, task logs, timing history, failed tasks). stdio by default, streamable HTTP in Compose, Pydantic-validated inputs, no SQL tool.
- `DomainAdapter` protocol with the retail adapter holding every business rule, and a support-triage stub that boots the same graph.
- LangGraph investigation graph: Planner, Reconciliation and Data-Quality running concurrently, Reporter, plus human review via `interrupt()` with a Postgres checkpointer.
- Structured model output with a two-retry re-prompt loop and adapter templates as the fallback; confidence bounded by a calibrated prior; the review gate can't be talked out of.
- Per-run tracing to `agent_steps`, mirrored to LangFuse when keys are set; `TracedLLM` refuses untraced calls.
- Incident reports and review decisions in Postgres, with ledger entries for every finding and decision.
- API: streaming chat over the graph (SSE), background scans, incidents, review queue actions, runs and traces.
- Screens: incident feed, review queue, streaming Ask ReconMind, traces list and run detail.
- Tests: MCP servers, full scans with review approve and reject, concurrency, every LLM call traced, domain-agnostic boot, and prompt injection against a model that obeys planted instructions.
- Compose: MCP servers as HTTP services and self-hosted LangFuse v3.
- ADRs 0007-0010.

## [phase-b] - 2026-09-18

### Added
- Seeded synthetic pipeline generator (`--seed 42`, byte-for-byte reproducible): 85 landing files, reference data, an Airflow-style DAG log with one failed task, dbt model YAML and manifest, data dictionary, and exact counts for every planted anomaly.
- Postgres schema through Alembic: raw transactions, reference tables, file loads, chat sessions, and an audit ledger that rejects UPDATE, DELETE and TRUNCATE at the database.
- Loader that maps submitter files by column name and records missing and unexpected columns per file.
- Hybrid retrieval: BM25 with an identifier-aware, stemmed tokenizer plus dense search, fused with reciprocal rank fusion; Pinecone behind `VECTOR_STORE=pinecone`; OpenAI embeddings as an option; dbt model YAML in the corpus.
- LLM fallback chain (OpenAI, Anthropic, Ollama) with cooldowns, `DEMO_MODE`, cost estimates, and an extractive answer when nothing is reachable.
- Chat session memory in Postgres, with short follow-up questions carrying the previous question into retrieval.
- 46-question golden set and a RAGAS runner with offline judges; CI fails below `evals/thresholds.yaml` and results are kept in `evals/history.csv`.
- Docs & runbooks screen with hybrid / dense / BM25 search side by side, and a document viewer.
- Docker Compose for Postgres, Ollama, API and web. The API image runs embeddings on onnxruntime and no longer ships torch.
- ADRs 0002-0006.

### Changed
- The ask page is now a conversation with session memory.
- Hybrid retrieval beats the Phase A dense baseline on the golden set: context precision 0.661 to 0.756, recall 0.844 to 0.911.

## [phase-a] - 2026-09-18

### Added
- Synthetic knowledge corpus: nine runbooks, five schema docs, five past incident write-ups.
- Markdown-aware chunking (section first, then size) with title and section carried into every chunk.
- Dense retrieval with sentence-transformers `all-MiniLM-L6-v2` and FAISS, cached on disk by corpus fingerprint.
- Single OpenAI-compatible LLM client (OpenAI or Ollama) with an extractive fallback when no model is reachable.
- FastAPI: `/healthz`, `/ask`, `/search`, `/corpus`.
- Next.js + shadcn/ui page for asking questions with cited sources.
- CI: ruff, black, mypy, pytest with an 80% coverage gate, gitleaks over full history, `next build`.
- Pre-commit hooks, Makefile, Dockerfile, Render blueprint and Railway config.
- Project deck (PPTX, PDF export, cover image) under `docs/slides`, with `make deck` to re-export.
