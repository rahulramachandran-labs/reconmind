# Deployment

The web app runs on Vercel and the API, with its Postgres, on Render. [`railway.json`](../railway.json) is included as an alternative for the API.

| | URL |
|---|---|
| Web app | [reconmind-labs.vercel.app](https://reconmind-labs.vercel.app) |
| API | [reconmind-labs-api.onrender.com](https://reconmind-labs-api.onrender.com/healthz) (interactive docs at `/docs`) |

## API on Render

1. Open [render.com/deploy?repo=…/reconmind](https://render.com/deploy?repo=https://github.com/rahulramachandran-labs/reconmind) and approve the blueprint in [`render.yaml`](../render.yaml). It creates the Docker web service and a free Postgres, and on every start the container runs migrations and loads the synthetic sample ([`scripts/start.sh`](../scripts/start.sh)).
2. Fill in the variables the blueprint leaves blank: `WRITE_TOKEN` (any long random string, e.g. `openssl rand -hex 24`) and, optionally, a model key and the LangFuse keys. A free tier is enough: `GROQ_API_KEY`, `GEMINI_API_KEY` or `OPENROUTER_API_KEY` (or the paid `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`). Once one is set, `/healthz` lists it under `llm_providers` and `/model` names the model that will answer. Everything else is set by the blueprint and explained in [`.env.example`](../.env.example).
3. With the service connected to the GitHub repo, every push to `main` redeploys it. Otherwise, use **Manual Deploy → Deploy latest commit**.

The image has no PyTorch: embeddings run on onnxruntime through fastembed, the MCP servers run in-process and the reranker is off, so the whole API fits a 512 MB instance ([ADR 0003](adr/0003-onnx-embeddings-in-the-container.md)).

## Web app on Vercel

Import `frontend/` as a Vercel project and set:

| Variable | Value |
|---|---|
| `NEXT_PUBLIC_API_URL`, `RECONMIND_API_URL` | The API URL |
| `RECONMIND_WRITE_TOKEN` | The same value as the API's `WRITE_TOKEN` |
| `AUTH_SECRET` | A random string (`openssl rand -base64 32`) |
| `AUTH_DEMO_MODE` | `true` lets visitors act as a shared demo reviewer |
| `AUTH_GITHUB_ID`, `AUTH_GITHUB_SECRET`, `AUTH_ALLOWED_GITHUB_LOGINS` | For real sign-in, with `AUTH_DEMO_MODE=false` |

Each variable is described in [`frontend/.env.example`](../frontend/.env.example). `make deploy` redeploys from the command line.

Anyone can read. Scans and review decisions go through the web app's server, which checks the session and forwards the call with the token, so the token never reaches a browser. Chat, ask and scan are rate limited per client.

## Scheduled scans

Add the API's write token as the repository secret `RECONMIND_WRITE_TOKEN`. [`refresh-demo.yml`](../.github/workflows/refresh-demo.yml) then wakes the API every six hours, starts a scan, waits for it, and has the API's model write up any finding that has no model write-up yet ([`scripts/regenerate_reports.py`](../scripts/regenerate_reports.py)); the outcome goes to the workflow summary. You can also run it by hand from the Actions tab, with *all* ticked to write every finding up again. `make regenerate-reports API=<url>` does the write-ups from your machine, with `WRITE_TOKEN` in the environment. A finding an earlier scan already reported is counted again rather than written up twice, so the review queue holds one item per problem ([ADR 0011](adr/0011-scheduled-scans-and-finding-fingerprints.md)).

## Free-tier notes

- **The database expires.** Render deletes free Postgres databases 30 days after they are created. The demo's `reconmind-db` was created on 2026-09-19, so it goes around 2026-10-19. When it does, apply the blueprint again or point `DATABASE_URL` at another Postgres; migrations and the sample load run on startup either way.
- **The instance sleeps.** A free instance spins down after 15 minutes without traffic, which is why scans come from GitHub Actions rather than a timer inside the API (`SCAN_INTERVAL_MINUTES` is kept for always-on servers). [`keep-warm.yml`](../.github/workflows/keep-warm.yml) pings it every ten minutes from 03:00 to 19:00 UTC until the date in the `KEEP_WARM_UNTIL` repository variable. Free instance hours are shared across a Render workspace, so it doesn't run around the clock.
- **Scheduled workflows pause.** GitHub disables scheduled workflows in repositories with no commits for 60 days. Re-enable them from the Actions tab if that happens.

## Running the containers yourself

```bash
docker compose --profile full up --build
```

This starts Postgres, both MCP servers over HTTP, the API, the web app, Ollama and a self-hosted LangFuse (UI on :3001, sign in as `admin@reconmind.local` / `reconmind-local`).
