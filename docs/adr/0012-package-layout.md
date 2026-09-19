# 0012. Package layout: one module per agent, shared code by concern

- Status: accepted
- Date: 2026-09-19

## Context

By 1.1.0 the backend had grown around the phases it was built in. All four agents lived in one `nodes.py`; the retail domain was a single 690-line `__init__.py`; `config.py`, `llm.py`, `rag.py`, `extractive.py`, `sessions.py` and `scheduler.py` sat loose at the top of `app/`; and there were two modules called `llm.py` (the provider chain and the agents' traced wrapper). The prompt text and passage formatting existed twice, once for `/ask` and once for the agents, and only the agents' copy stripped tags a document could use to break out of its context block.

Someone opening the repo for the first time had to read several large files before they could see the shape of the system.

## Decision

- **One module per agent** under `app/agents/`: `planner.py`, `specialists.py`, `reporter.py`, `answerer.py` and `review.py` (the human-in-the-loop checkpoints). `graph.py` only wires them. What every node receives is in `deps.py`. The run store is a package with `sql.py` and `memory.py`.
- **Shared code grouped by concern:** `app/core/` (settings, logging), `app/llm/` (`providers.py`, `traced.py`, `structured.py`), `app/rag/` (`prompts.py`, `answer.py`, `extractive.py`), `app/memory/` (chat sessions).
- **One copy of the prompts and passage formatting** in `app/rag/prompts.py`, used by both `/ask` and the agents. `/ask` now sanitises passages too.
- **The retail domain split by what changes together:** `rules.py` (keys and thresholds), `checks.py` (what each specialist checks), `writeups.py` (severity rubric and wording) and `adapter.py` (the roster that wires them). The "latest file per submitter" logic that the volume check and the dashboard each had becomes one helper.
- **`api/routes.py` becomes `api/knowledge.py`** (ask, search, corpus, sessions), with `/healthz` in `api/health.py`.
- `RETRIEVAL_K` is removed; it was never read.

Behaviour is otherwise unchanged: same prompts, prompt versions, thresholds and API.

## Consequences

- The file tree now reads like the architecture diagram, and each agent can be read on its own.
- The domain-agnostic test walks `app/agents/` recursively, so the new `store/` package is covered by the rule that no agent module imports a domain.
- Import paths changed. Nothing outside this repository imports them.
