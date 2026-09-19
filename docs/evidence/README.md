# Captured evidence

Raw responses from a local ReconMind stack, captured by [`scripts/capture_readme_evidence.py`](../../scripts/capture_readme_evidence.py). The README's report, trace excerpt and results are quoted from these files.

| | |
|---|---|
| Captured | 2026-09-19T16:17:46Z |
| Commit | `0cf0fff` |
| API | 1.1.0, providers `ollama` |
| Model calls went to | ollama/qwen2.5:1.5b |
| Scan run | `d36c5c4a-d20e-4629-9b27-d433f076755d` (paused_review) |
| Scan wall time | 208.7 s |
| Scan steps | 5 agent nodes, 30 MCP tool calls, 4 retrievals, 7 model calls |
| Scan cost | $0.0000 (9585 prompt + 1912 completion tokens) |
| ask-mobile run | `c254aa4c-a147-4b9c-beec-dbd97ca6eaab` (completed): Did the MOBILE file have a schema problem on 2026-06-16? |
| ask-runbook run | `e3b621c1-1e09-4d94-b6fd-9584e3488c6d` (paused_plan): Which file wins when a submitter resends the same day? |
| Tests | 152 passed, 0 failed, 93.27% coverage |

| Severity | Finding | Status | Written by |
|---|---|---|---|
| S1 | S1003_20260616_0216_MOBILE.txt renamed channel_basket_id to basket_ref | pending_review | template |
| S2 | LOC-0517 also reporting as OUT-1071 (3.0% of rows) | published | ollama |
| S2 | Resent file S1002_20260612_1120_ECOMM.txt supersedes 88 rows | published | ollama |
| S2 | S1001 2026-06-18: 110 rows, 40% below its 7-day average | published | ollama |

`Written by` is who wrote the root cause, fix and open questions: the model's provider, or `template` when the model's reply failed validation twice. Counts, severity and the problem statement always come from the deterministic checks.

| File | What it is |
|---|---|
| `summary.json` | Everything below, condensed: counts, models, findings, tests, RAGAS |
| `healthz.json`, `model.json` | `GET /healthz` and `GET /model` before the scan |
| `scan-run.json` | `GET /runs/{id}` for the scan: every traced step |
| `scan-reports.json` | The incident reports the scan produced |
| `incident-key-drift.json` | The key-drift report quoted in the README |
| `dashboard.json` | `GET /dashboard` after the scan |
| `ask-mobile-*.json` | Events streamed for the MOBILE question, and its run |
| `ask-runbook-*.json` | Events streamed for a runbook question, and its run |
| `tests.txt` | The tail of `make test`: pass count and coverage |

Reproduce: start a freshly seeded stack with `make dev`, then run `uv run python scripts/capture_readme_evidence.py`.
