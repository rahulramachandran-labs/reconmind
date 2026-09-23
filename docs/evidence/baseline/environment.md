# Environment, as deployed

Names only; no values. Read from [`render.yaml`](../../../render.yaml),
[`frontend/.env.example`](../../../frontend/.env.example) and the two keys added by hand in the
Render dashboard. This is the list the hardening work must not add to: nothing new may be
required for either side to boot.

## Render (API)

| Variable | Source | Value in the blueprint |
|---|---|---|
| `APP_ENV` | blueprint | `production` |
| `DATABASE_URL` | managed database | connection string of `reconmind-db` |
| `SEED_SAMPLE` | blueprint | `true` |
| `MCP_TRANSPORT` | blueprint | `inprocess` |
| `SCAN_INTERVAL_MINUTES` | blueprint | `0` |
| `RERANKER` | blueprint | `none` |
| `OLLAMA_BASE_URL` | blueprint | empty |
| `LANGFUSE_HOST` | blueprint | `https://cloud.langfuse.com` |
| `CORS_ORIGINS` | blueprint | `["https://reconmind-labs.vercel.app"]` |
| `WRITE_TOKEN` | dashboard (`sync: false`) | set |
| `GROQ_API_KEY` | dashboard (`sync: false`) | set |
| `GEMINI_API_KEY` | dashboard (`sync: false`) | set |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OPENROUTER_API_KEY` | dashboard (`sync: false`) | unset |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | dashboard (`sync: false`) | unset |

`DEMO_MODE` is **not** set, and [`app/core/config.py`](../../../app/core/config.py) defaults it to
`false`. The demo costs nothing because the only keys set are free-tier ones, not because demo mode
is on. `healthCheckPath` is `/healthz` and `autoDeploy` is `true`.

## Vercel (web app)

`NEXT_PUBLIC_API_URL`, `RECONMIND_WRITE_TOKEN` (the same value as the API's `WRITE_TOKEN`),
`AUTH_SECRET`, `AUTH_DEMO_MODE`, `AUTH_GITHUB_ID`, `AUTH_GITHUB_SECRET`,
`AUTH_ALLOWED_GITHUB_LOGINS`.

## What this means for the production guard

With `APP_ENV=production`, a `WRITE_TOKEN`, a `DATABASE_URL` and a `CORS_ORIGINS` holding one
explicit origin, a guard that refuses to start on a missing write token, a missing database or a
wildcard origin would let this deployment through unchanged.
