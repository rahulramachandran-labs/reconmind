# Changelog

All notable changes, grouped by build phase. Dates are UTC.

## [Unreleased]

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
