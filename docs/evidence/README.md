# Captured evidence

Raw responses from a local ReconMind stack, captured by [`scripts/capture_readme_evidence.py`](../../scripts/capture_readme_evidence.py). The README's report, trace excerpt and results are quoted from these files.

| | |
|---|---|
| Captured | 2026-09-19T19:00:08Z |
| Commit | `35d6309` |
| API | 1.1.0, providers `groq, gemini, ollama` |
| Model calls went to | groq/openai/gpt-oss-120b |
| Scan run | `b5444ae1-f162-41ff-8a82-28f65425be9c` (paused_review) |
| Scan wall time | 14.8 s |
| Scan steps | 5 agent nodes, 30 MCP tool calls, 4 retrievals, 5 model calls |
| Scan cost | $0.0000 (5602 prompt + 2161 completion tokens) |
| ask-mobile run | `08cdde6e-8acc-472b-8034-f4dff77cc71f` (completed): Did the MOBILE file have a schema problem on 2026-06-16? |
| ask-runbook run | `dcccae9c-98fd-4806-a922-8e445a310b1c` (completed): Which file wins when a submitter resends the same day? |
| ask-follow-up run | `49233696-56a7-4ba1-9f27-79da8dd07e59` (completed): What should we check before reprocessing that day? |
| S1 written up again | HTTP 200, `analysis_by: model`, gemini/gemini-3.6-flash, 4239 ms |
| S1 signed off | run resumed: approve -> published |
| Second scan | `1921304f-7ef9-424a-a16a-5f4c21ff7130` (completed): S1: Missing channel_basket_id in S1003 file blocks deduplication |
| Tests | 158 passed, 0 failed, 93.17% coverage |

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
| `regenerate-s1.json` | `POST /incidents/{id}/regenerate` on the S1: both write-ups |
| `review-s1.json` | The S1 approved with a note; the paused run resumes |
| `rescan-run.json`, `incidents-after.json` | A second scan, and the feed after it |
| `tests.txt` | The tail of `make test`: pass count and coverage |

Reproduce: start a freshly seeded stack with `make dev`, then run `uv run python scripts/capture_readme_evidence.py`.
