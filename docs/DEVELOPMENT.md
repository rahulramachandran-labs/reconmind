# Development

## Setup

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 20+ and Docker. [Ollama](https://ollama.com) is optional.

```bash
make bootstrap   # uv sync, npm ci, git hooks, .env from .env.example, frontend/.env.local with a fresh AUTH_SECRET
make dev         # Postgres in Docker, migrations, the synthetic sample, then the API on :8000 and the web app on :3000
```

Port 5432 already taken? Set `POSTGRES_PORT` and the port in `DATABASE_URL` in `.env`. Every setting is explained in [`.env.example`](../.env.example) and [`frontend/.env.example`](../frontend/.env.example).

For a step-by-step tour of a run once it is up, follow the [runbook in the README](../README.md#runbook-walk-through-the-whole-flow-locally).

## Make targets

| Target | What it does |
|---|---|
| `make dev` | `db` and `seed`, then the API and web app together (Ctrl-C stops both) |
| `make api`, `make web` | Just one of them, with reload |
| `make db` | Start Postgres and apply migrations |
| `make seed` | Load the committed synthetic sample into `DATABASE_URL` (files already loaded are skipped) |
| `make test` | pytest with the 80% coverage gate |
| `make test-fast` | Skip the tests that load the real embedding model |
| `make lint` | ruff, black, mypy, eslint |
| `make fmt` | ruff fixes and black |
| `make eval` | RAGAS gate on the golden set; appends to `evals/history.csv` |
| `make index` | Build the dense index into `.index/` |
| `make deck` | Re-export the slide deck to PDF and refresh the cover image |
| `make deploy` | Deploy the web app to Vercel |

## Tests

```bash
make test                      # everything: unit, integration, chaos
uv run pytest tests/unit       # fast, no database needed
uv run pytest -m chaos -v      # plant each anomaly with the generator and check the right agent catches it
```

Integration tests use the Postgres from `make db` and skip themselves when it isn't reachable. They cover the loader, both MCP servers over a real client, the agent graph end to end, the API, prompt injection and the second domain.

## The data generator

```bash
uv run python scripts/generate_synthetic_pipeline.py --help
uv run python scripts/generate_synthetic_pipeline.py --seed 7 --out /tmp/p --only key_drift
```

The committed sample in `data/sample/` is `--seed 42`; a test regenerates it and fails if one byte differs.

## Adding a domain

1. Create `app/domain/<name>/` with a class that satisfies [`DomainAdapter`](../app/domain/protocol.py): a roster of specialists, checks, a severity rubric and write-up templates. [`example_support_triage`](../app/domain/example_support_triage) is the smallest working example.
2. Register it in [`app/domain/registry.py`](../app/domain/registry.py) and set `DOMAIN_ADAPTER`.
3. Point `CORPUS_DIR` at the domain's runbooks, and give the checks their data through MCP tools.

Nothing under `app/agents/` changes; a test fails if an agent module imports a domain.

## Conventions

- Conventional commits (`feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `test:`).
- Pre-commit runs ruff, black, mypy on changed files, and gitleaks.
- CI runs lint, types, tests with coverage, the RAGAS gate, gitleaks over the full history and `next build`.
- Decisions that would be expensive to reverse get an [ADR](adr/README.md).
- Run the Next.js dev server through `make web` or `make dev`.
