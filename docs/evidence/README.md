# Captured evidence

Raw responses from a local ReconMind stack, captured by [`scripts/capture_readme_evidence.py`](../../scripts/capture_readme_evidence.py). The README's report, trace excerpt and results are quoted from these files.

| | |
|---|---|
| Captured | 2026-09-23T06:09:54Z |
| Commit | `1bf31ac` |
| API | 1.1.0, providers `groq, gemini, ollama` |
| Model calls went to | groq/openai/gpt-oss-120b |
| Scan run | `9bda1e0c-4add-4ac7-8351-8434ccba88aa` (paused_review) |
| Scan wall time | 27.2 s |
| Scan steps | 5 agent nodes, 30 MCP tool calls, 4 retrievals, 5 model calls |
| Scan cost | $0.0000 (5714 prompt + 2283 completion tokens) |
| ask-mobile run | `0c4e7eea-10a4-446c-9eff-f2655f564386` (completed): Did the MOBILE file have a schema problem on 2026-06-16? |
| ask-runbook run | `1853377d-56f0-43f4-8866-ff297b3358b2` (completed): Which file wins when a submitter resends the same day? |
| ask-follow-up run | `571f7a08-f5b4-41b8-9ea9-9b0288455bb6` (completed): What should we check before reprocessing that day? |
| ask-explore run | `1799b95e-a9aa-4a96-aa6c-af9f32c1c95d` (completed): Show me which submitter sent the fewest rows on 2026-06-18, and when its file landed. |
| S1 written up again | HTTP 200, `analysis_by: model`, groq/openai/gpt-oss-120b, 1403 ms |
| S1 signed off | run resumed: approve -> published |
| Second scan | `c7feabd0-fd54-43f7-b2ba-821aee4ba713` (completed): S1: Missing channel_basket_id in S1003_20260616_0216_MOBILE.txt blocks dedup |
| Tests | 172 passed, 0 failed, 92.58% coverage |

| Severity | Finding | Status | Written by |
|---|---|---|---|
| S1 | S1003_20260616_0216_MOBILE.txt renamed channel_basket_id to basket_ref | pending_review | groq/openai/gpt-oss-120b |
| S2 | LOC-0517 also reporting as OUT-1071 (3.0% of rows) | published | groq/openai/gpt-oss-120b |
| S2 | Resent file S1002_20260612_1120_ECOMM.txt supersedes 88 rows | published | groq/openai/gpt-oss-120b |
| S2 | S1001 2026-06-18: 110 rows, 40% below its 7-day average | published | groq/openai/gpt-oss-120b |

`Written by` is who wrote the root cause, fix and open questions: the model, or `template` when no model reply validated. Counts, severity and the problem statement always come from the deterministic checks.

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
| `ask-follow-up-*.json` | A follow-up in the same session, and its run |
| `ask-explore-*.json` | A data question the Explorer answers with tools it picks |
| `regenerate-s1.json` | `POST /incidents/{id}/regenerate` on the S1: both write-ups |
| `review-s1.json` | The S1 approved with a note; the paused run resumes |
| `rescan-run.json`, `incidents-after.json` | A second scan, and the feed after it |
| `tests.txt` | The tail of `make test`: pass count and coverage |

Reproduce: start a freshly seeded stack with `make dev`, then run `uv run python scripts/capture_readme_evidence.py`.
