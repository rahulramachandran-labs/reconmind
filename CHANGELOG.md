# Changelog

All notable changes, grouped by build phase. Dates are UTC.

## [Unreleased]

## [1.1.0] - 2026-09-19

A model now does the writing, and everything a reviewer needs to check that is in the repository.

### Added
- **Free-tier models.** Groq (`openai/gpt-oss-120b`), Google Gemini (`gemini-3.6-flash`, thinking off; new keys can no longer use 2.5 Flash) and OpenRouter (`deepseek/deepseek-v4-flash-0731:free`) join the fallback chain after OpenAI and Anthropic and before Ollama, through the OpenAI-compatible API, with the same cooldown, cost accounting and tracing. Free-tier calls retry a 429 before falling through, record $0, and run at most `LLM_CONCURRENCY` (2) at a time. Startup logs which providers are active and which were skipped, and why (for example `no GROQ_API_KEY`).
- **Both write-ups on every report.** The template's (`template`) and, when a model's reply validated, the model's (`model_analysis`, with provider, model, latency, tokens, cost and prompt version). `analysis_by` is `model` or `template`. The problem statement and counts stay the checks' in both.
- **An Explorer agent** (ADR 0013). A question about the data that isn't one of the four failure types ("which submitter sent the fewest rows on the 18th, and when did its file land?") goes to the new `explore` intent: the model gets the read-only MCP tools as function calls, may call up to three, and answers from what they returned. Every call is traced; with no tool-capable model the runbooks answer instead.
- **A grounding check on model write-ups.** A reply that states a time, id or multi-digit number that appears nowhere in the finding, its evidence or the passages is sent back to the model with the offending values named, and after three tries the template stands.
- `POST /incidents/{id}/reopen` (write token) puts a decided finding back in the review queue, and a decision on a reopened finding is applied directly since its run has finished. `refresh-demo.yml` reopens the S1 so each reviewer can try the sign-off.
- Chat memory is a LangChain `BaseChatMessageHistory` over the session store, and the answer prompt is a `ChatPromptTemplate` with a `MessagesPlaceholder`, shared by `/ask` and the agents.
- `POST /incidents/{id}/regenerate` (write token) runs the finding's checks again and has the active model write it up, as its own traced run. `make regenerate-reports` and `scripts/regenerate_reports.py` do it for every finding without a model write-up.
- `GET /model`: the provider and model the next call goes to, the fallback order, and whether the last call fell back. `/healthz` adds `llm_models`, and the chat stream's `answer` event names its model and any providers it fell back past.
- **Web.** *Deterministic checks*, *Model analysis* and *Side by side* on every report, with the model's provider, latency, tokens and cost; a header pill naming the active model; each chat answer names who answered and says plainly when it was extractive; a notice while the free-tier API wakes up; `/verify`, which lines up each planted anomaly with its finding, its chaos test and both write-ups.
- **Scheduled work.** `refresh-demo.yml` (replaces `scheduled-scan.yml`) scans every six hours and has the model write up new findings; `keepalive.yml` (replaces `keep-warm.yml`) keeps the free instance awake 03:00-19:00 UTC until `KEEP_ALIVE_UNTIL` (default 2026-10-03); `reseed.yml` reloads the sample into a recreated database, then scans and writes up; `make reseed`.
- **CI.** A `fresh clone` job runs `make bootstrap && make dev` in an empty directory and checks that the API, the web app and `/ask` answer. A `ragas (model answers)` job, by hand and on release tags, scores Groq's answers with offline judges and with a different model judging (`--judge llm --judge-model groq/qwen/qwen3.8-27b`). With the `RENDER_DEPLOY_HOOK_URL` secret set, CI calls the Render deploy hook once every check on `main` passes.
- **Evidence.** `scripts/capture_readme_evidence.py` plays every scenario a reviewer would try against a running stack (scan, investigation question, runbook question and follow-up, the S1 written up again and signed off, a second scan) and saves the raw responses and test counts to `docs/evidence/`. `scripts/update_docs_from_evidence.py` then rewrites the README's trace excerpt, quoted report, Results, screens and test counts, and writes `docs/VERIFY.md` and `docs/COURSE_MAPPING.md`, with code links pinned to the commit.
- Eleven screenshots in `docs/screenshots/`, a two-minute captioned walkthrough in `docs/demo.mp4` (`scripts/record_demo.py --screenshots`, `--video`), and `docs/demo.gif` cut from it.
- `docs/REVIEWER_GUIDE.md`, an evaluate-in-five-minutes box at the top of the README, and a model-answered row in the evaluation table.
- Findings are fingerprinted: a scan that sees a finding an earlier scan reported increments its `seen_count` and `last_seen_at` and writes `finding.seen_again` to the ledger instead of creating a new report. Repeats never pause a run, and rejected findings stay rejected. The incident feed shows how many scans have seen each finding. ADR 0011.

### Changed
- README rewritten for a first-time reader: what ReconMind does and how a run flows end to end first, then results from a real run, screens, a step-by-step local runbook, the project structure and production readiness. Detail moved to `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DEPLOYMENT.md`, `docs/EVALUATION.md` and `docs/DEVELOPMENT.md`.
- Backend reorganised (ADR 0012): one module per agent (`planner`, `specialists`, `reporter`, `answerer`, `review`), `app/core`, `app/llm`, `app/rag` and `app/memory` packages, the run store split into Postgres and in-memory modules, and the retail domain split into `rules`, `checks`, `writeups` and `adapter`.
- `.env.example` explains every setting, and `frontend/.env.example` does the same for the web app.
- `--judge llm` picks a judge that isn't the answering model, and only faithfulness and relevancy are model-judged; retrieval is still scored against the labelled chunks.
- An empty reply from a model counts as a failed call, so the chain moves on.
- A rescan doesn't ask the model again about a finding it has already written up, and replaces a template-only write-up with the model's when a model is available, so a deployment that ran without a key catches up on its next scan.
- The Planner sees the last turns of the conversation, and "check" alone no longer marks a question as an investigation, so "what should we check before reprocessing that day?" is answered from the runbooks. The specialists' prompt says not to treat a past incident's cause as this one's.
- `keepalive.yml` starts hourly and pings every five minutes for fifty minutes, because GitHub starts scheduled workflows late; it runs until 2026-10-19, when the free database expires.
- Dashboard "open findings" counts what the latest scan saw, minus rejected ones. Render runs with `SCAN_INTERVAL_MINUTES=0`.

### Fixed
- Migration 0004 folds findings duplicated before fingerprints existed: one report per finding keeps the seen count and latest sighting, the copies point at it through `duplicate_of` and leave the feed and the review queue, and runs that were waiting only on copies are marked `superseded`. Nothing is deleted; each fold is in the ledger.
- A template cites a past incident only when it matches the finding type; the duplicate-submission template had been citing the schema-drift incident.
- The trace page groups each step under the agent that recorded it; with two specialists running at once, one agent's tool calls had appeared under the other.
- `/ask` strips context tags from retrieved passages, as the agents already did; the two paths share one prompt module.
- The header no longer overlaps at desktop widths, and the chat says why a write-up came from a template instead of claiming no model was reachable.
- Alembic no longer disables the app's loggers when migrations run in-process.
- The package, the API and the web app all report 1.1.0.

### Removed
- The `RETRIEVAL_K` setting, which nothing read.

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
