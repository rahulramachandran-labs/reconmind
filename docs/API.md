# API reference

The API is FastAPI; interactive docs are served at `/docs` on any running instance ([live](https://reconmind-labs-api.onrender.com/docs)). Reads are open. Calls marked *writer* need `Authorization: Bearer <WRITE_TOKEN>` when the API has a token configured; the web app adds it on its server after checking the user's session, and passes the reviewer's name in `X-Reviewer`.

## Agents and review

| Method | Path | What it does |
|---|---|---|
| `POST` | `/chat/stream` | `{question, session_id?}`: runs the agent graph and streams server-sent events (below). Rate limited. |
| `POST` | `/scan` | *writer.* Starts a full scan in the background and returns `{run_id}` (202). Rate limited. |
| `GET` | `/runs`, `/runs/{id}` | Agent runs with status, cost and latency; one run with every traced step and its reports |
| `GET` | `/incidents`, `/incidents/{id}` | Incident reports, filterable by `status` and `severity` |
| `POST` | `/incidents/{id}/regenerate` | *writer.* Runs the finding's checks again and has the active model write it up, as its own traced run. Returns the report with `template` and `model_analysis` side by side; 503 if no model's reply validated, 409 if the checks no longer find it. Rate limited. |
| `POST` | `/incidents/{id}/reopen` | *writer.* `{note?}`: puts a published or rejected finding back in the review queue; the earlier decision stays in the ledger |
| `GET` | `/review` | Reports and plans waiting for a person |
| `POST` | `/review/reports/{id}` | *writer.* `{decision: approve \| reject \| annotate, note?}`. The run resumes once every paused report in it has a decision. |
| `POST` | `/review/runs/{id}` | *writer.* Approve or reject a plan the Planner was unsure about, optionally choosing the specialists |
| `GET` | `/dashboard` | Volume against the trailing week, last DAG run, open findings, today's model usage |

## Retrieval without the agents

| Method | Path | What it does |
|---|---|---|
| `POST` | `/ask` | `{question, k?, session_id?}`: retrieve and answer with citations. Returns the answer, sources, provider, model, tokens, cost and latency. Rate limited. |
| `GET` | `/search?q=&k=&mode=hybrid\|dense\|bm25` | Retrieval only, with the dense and BM25 rank of each hit |
| `GET` | `/corpus`, `/corpus/{doc_id}` | The indexed documents |
| `GET` | `/sessions/{id}/messages` | A chat session's history |
| `GET` | `/healthz` | Status, version, chunk count, retriever, model providers, database |
| `GET` | `/model` | The provider and model the next call goes to, the fallback order, and whether the last call fell back |

## Chat stream events

`POST /chat/stream` answers with `text/event-stream`. The event name is the `type`; the data is JSON.

| Event | When | Data |
|---|---|---|
| `session` | First | `session_id` (reuse it to continue the conversation) |
| `run` | Run created | `run_id`, `trace_id`, `trace_url` |
| `plan` | Planner done | `intent` (`answer`, `investigate`, `explore` or `unclear`), `specialists`, `confidence`, `rationale`, `planned_by`, `scope`, `needs_review` |
| `node` | Each agent finishes | `node` |
| `finding` | Each specialist finding | `specialist`, `finding_type`, `severity`, `title`, `affected_records` |
| `report` | Reporter done, one per report | The full incident report |
| `summary` | Reporter done | `headline`, `summary` |
| `answer` | Runbook questions, and the Explorer's answers | `text`, `provider`, `model`, `fallbacks` (providers it fell back past), `sources` |
| `paused` | Waiting for a person | `kind` (`plan` or `reports`) and what needs deciding |
| `done` | Finished | `latency_ms`, `llm_calls`, `tool_calls`, token counts, `cost_usd`, `trace_url` |
| `error` | Something failed | `message` |

```bash
curl -N localhost:8000/chat/stream -H 'content-type: application/json' \
  -d '{"question": "Did the MOBILE file have a schema problem on 2026-06-16?"}'
```
