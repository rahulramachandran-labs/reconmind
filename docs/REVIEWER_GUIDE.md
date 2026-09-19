# Reviewer guide

A checklist for evaluating ReconMind, from five minutes on the live app to a full local run. Every claim in the README has something here you can open or run to check it.

## Five minutes, in the browser

1. Open the [API health check](https://reconmind-labs-api.onrender.com/healthz). The free instance sleeps when idle, so the first request can take up to a minute. Wait for `"status":"ok"` and `"database":true`.
2. Open [reconmind-labs.vercel.app](https://reconmind-labs.vercel.app), choose **Sign in**, then **Continue as the demo reviewer**.
3. **Dashboard:** the chart shows 14 days of volume, with 2026-06-18 visibly short. Click **Run a scan**. The *Open findings* tile shows four findings, one S1 and three S2.
4. **Review queue:** the S1 schema-drift finding is waiting, with the reason it paused. Add a note and approve it. The decision is recorded under the demo reviewer's name.
5. **Ask ReconMind:** ask *Did the MOBILE file have a schema problem on 2026-06-16?* and watch the Planner route it to the Data-Quality agent only.
6. **Traces:** open that run to see every agent step, MCP tool call, retrieval and model call, with latency, tokens and cost.
7. **Docs & runbooks:** search `basket_ref ContractViolation` and switch between Hybrid, Dense and BM25 to see why hybrid search is the default.

The hosted API answers with templates and extractive answers unless a model key is set on the server; `/healthz` lists the providers it has under `llm_providers`. The same screens with a model writing the explanations are in the README's screenshots, captured locally.

## Twenty minutes, locally

Follow the twelve-step [runbook in the README](../README.md#runbook-walk-through-the-whole-flow-locally). It needs Python 3.12 with uv, Node 20+ and Docker; `make bootstrap && make dev` starts everything with the seeded data. [Ollama](https://ollama.com) with `qwen2.5:1.5b`, or any key in [`.env.example`](../.env.example), makes a model write the explanations.

## What to check, and where

| Claim | Check it here |
|---|---|
| It's multi-agent | [`app/agents/graph.py`](../app/agents/graph.py) wires a Planner, two specialists that run in parallel, a Reporter and human review; one file per agent in [`app/agents/`](../app/agents) |
| A model really writes the reports | [`docs/evidence/incident-key-drift.json`](evidence/incident-key-drift.json): `analysis_by: ollama`, and the model calls with tokens in [`scan-run.json`](evidence/scan-run.json) |
| Facts are measured, not generated | [`app/domain/retail_recon/checks.py`](../app/domain/retail_recon/checks.py); every report's counts match [`expected_anomalies.json`](../data/sample/expected_anomalies.json) (README, *Results*) |
| Tools go through MCP | [`mcp_servers/`](../mcp_servers) and the 30 tool calls in [`scan-run.json`](evidence/scan-run.json) |
| Retrieval is hybrid and measured | [`app/retrieval/`](../app/retrieval), the RAGAS rows in [`evals/history.csv`](../evals/history.csv), [docs/EVALUATION.md](EVALUATION.md) |
| People sign off serious findings | [`app/agents/review.py`](../app/agents/review.py) (`interrupt()`), the S1 `pending_review` in [`scan-reports.json`](evidence/scan-reports.json) |
| Everything is traced | [`app/observability/tracer.py`](../app/observability/tracer.py); a model call outside a traced run raises `UntracedCall` |
| It is tested | 152 tests, 93% coverage: [`docs/evidence/tests.txt`](evidence/tests.txt); CI on every push: [Actions](https://github.com/rahulramachandran-labs/reconmind/actions/workflows/ci.yml) |
| Prompt injection is handled | [`tests/integration/test_prompt_injection.py`](../tests/integration/test_prompt_injection.py) |
| The agents are domain-agnostic | [`app/domain/protocol.py`](../app/domain/protocol.py), the second domain in [`app/domain/example_support_triage/`](../app/domain/example_support_triage), and [`test_domain_agnostic.py`](../tests/integration/test_domain_agnostic.py) |
| Each course module maps to code | The *Course concepts applied* table in the [README](../README.md#course-concepts-applied), with pinned links to lines and tests |

## Known limits

- The hosted demo runs on free tiers: the API sleeps after 15 idle minutes and its database expires around 2026-10-19 ([docs/DEPLOYMENT.md](DEPLOYMENT.md)).
- Without a model key on the server, the hosted explanations come from templates. The design keeps every number deterministic either way.
- All data is synthetic, generated from a fixed seed.
