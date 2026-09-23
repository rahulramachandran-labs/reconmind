# Getting around ReconMind

A walkthrough, from five minutes on the live app to a full local run. Every claim in the README has something here you can open or run for yourself.

## Five minutes, in the browser

1. Open the [API health check](https://reconmind-labs-api.onrender.com/healthz). The free instance sleeps when idle, so the first request can take up to a minute. Wait for `"status":"ok"` and `"database":true`.
2. Open [reconmind-labs.vercel.app](https://reconmind-labs.vercel.app), choose **Sign in**, then **Continue as the demo reviewer**.
3. **Dashboard:** the chart shows 14 days of volume, with 2026-06-18 visibly short. Click **Run a scan**. The *Open findings* tile shows four findings, one S1 and three S2.
4. **Review queue:** the S1 schema-drift finding is waiting, with the reason it paused. Add a note and approve it. The decision is recorded under the demo reviewer's name. (Every six hours the refresh workflow reopens it, so the sign-off is always there to try.)
5. **Ask ReconMind:** ask *Did the MOBILE file have a schema problem on 2026-06-16?* and watch the Planner route it to the Data-Quality agent only. Then ask *Show me which submitter sent the fewest rows on 2026-06-18, and when its file landed.*: it goes to the Explorer, which picks the tools itself.
6. **Traces:** open that run to see every agent step, MCP tool call, retrieval and model call, with latency, tokens and cost.
7. **Docs & runbooks:** search `basket_ref ContractViolation` and switch between Hybrid, Dense and BM25 to see why hybrid search is the default.
8. **Verify:** each planted anomaly beside the finding it produced, the chaos test that proves it, and the template's and the model's write-ups side by side. Ask it anything and open the trace.

`/healthz` lists the model providers the API has under `llm_providers`, and `/model` names the one answering now. If the free instance is asleep and you'd rather not wait, the same walkthrough is recorded in [demo.mp4](demo.mp4), and the README's screenshots come from the same flow.

## Twenty minutes, locally

Follow the twelve-step [runbook in the README](../README.md#runbook-walk-through-the-whole-flow-locally). It needs Python 3.12 with uv, Node 20+ and Docker; `make bootstrap && make dev` starts everything with the seeded data. A free Groq key in `.env` as `GROQ_API_KEY` makes a model write the explanations, as on the hosted demo; any other key in [`.env.example`](../.env.example), or a local Ollama, works too.

## What to check, and where

| Claim | Check it here |
|---|---|
| It's multi-agent | [`app/agents/graph.py`](../app/agents/graph.py) wires a Planner, two specialists that run in parallel, a Reporter, an Explorer and human review; one file per agent in [`app/agents/`](../app/agents) |
| The model makes decisions | The Explorer chooses which MCP tools to call ([`explorer.py`](../app/agents/explorer.py), [ADR 0013](adr/0013-bounded-tool-use-for-open-questions.md)); the `explore` step in [`ask-explore-run.json`](evidence/ask-explore-run.json) lists the calls it asked for |
| A model really writes the reports | [`docs/evidence/incident-key-drift.json`](evidence/incident-key-drift.json): `analysis_by: model` with the provider, model, latency and tokens under `model_analysis`, and every model call in [`scan-run.json`](evidence/scan-run.json) |
| Facts are measured, not generated | [`app/domain/retail_recon/checks.py`](../app/domain/retail_recon/checks.py); every report's counts match [`expected_anomalies.json`](../data/sample/expected_anomalies.json) (README, *Results*) |
| Tools go through MCP | [`mcp_servers/`](../mcp_servers) and the 30 tool calls in [`scan-run.json`](evidence/scan-run.json) |
| Retrieval is hybrid and measured | [`app/retrieval/`](../app/retrieval), the RAGAS rows in [`evals/history.csv`](../evals/history.csv), [docs/EVALUATION.md](EVALUATION.md) |
| A finding is listed once, however often it is seen | Fingerprints and `seen_count` in [`app/agents/store/sql.py`](../app/agents/store/sql.py), the fold in [migration 0004](../migrations/versions/0004_fold_duplicate_findings.py), and `onePerFinding` in [`frontend/src/lib/api.ts`](../frontend/src/lib/api.ts) for anything an older deployment wrote ([ADR 0011](adr/0011-scheduled-scans-and-finding-fingerprints.md)) |
| People sign off serious findings | [`app/agents/review.py`](../app/agents/review.py) (`interrupt()`), the S1 `pending_review` in [`scan-reports.json`](evidence/scan-reports.json) |
| Everything is traced | [`app/observability/tracer.py`](../app/observability/tracer.py); a model call outside a traced run raises `UntracedCall` |
| It is tested | [`docs/evidence/tests.txt`](evidence/tests.txt) for the counts and coverage; CI on every push, including a fresh-clone run of `make bootstrap && make dev`: [Actions](https://github.com/rahulramachandran-labs/reconmind/actions/workflows/ci.yml) |
| Prompt injection is handled | [`tests/integration/test_prompt_injection.py`](../tests/integration/test_prompt_injection.py) |
| The agents are domain-agnostic | [`app/domain/protocol.py`](../app/domain/protocol.py), the second domain in [`app/domain/example_support_triage/`](../app/domain/example_support_triage), and [`test_domain_agnostic.py`](../tests/integration/test_domain_agnostic.py) |
| Each course module maps to code | [COURSE_MAPPING.md](COURSE_MAPPING.md), with pinned links to the lines and the covering test |
| Planted problems are found, and proven | [VERIFY.md](VERIFY.md) and the live [/verify](https://reconmind-labs.vercel.app/verify) page |

## Known limits

- The hosted demo runs on free tiers: the API sleeps after 15 idle minutes and its database expires around 2026-10-19 ([docs/DEPLOYMENT.md](DEPLOYMENT.md)).
- The hosted demo writes with Groq's free tier, which limits tokens per minute; when it runs out, calls fall through to the next provider and, last, to the template. Every report says which wrote it, and every number is deterministic either way.
- All data is synthetic, generated from a fixed seed.
