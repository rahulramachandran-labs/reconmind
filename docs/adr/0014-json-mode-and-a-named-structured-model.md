# 0014. JSON mode, and a named model for structured output

Date: 2026-09-23

## Status

Accepted.

## Context

Every incident write-up, plan and run summary is a Pydantic model the reply has to validate
against. A live browser session reported that all of the hosted findings said `template only`,
and the assumption was that Groq's replies were failing that validation.

Pulling the live trace showed the opposite. The `analyse:schema_drift` step of run
`f0327b81` came back from `groq/openai/gpt-oss-120b` as 1,694 characters of valid JSON, in one
attempt, with no retry. The hosted findings are template-only because they were written on
2026-09-19, before any model key was set, and the deployed build has no path that replaces a
template write-up with a model one: a later scan counts the finding as seen again and reuses
what is stored. `POST /incidents/{id}/regenerate` and the rescan upgrade both exist on `main`
and have never been deployed.

That left a real question anyway: is the model that answers prose the right one to ask for
JSON, and does asking for JSON mode help? Measured on the same finding, three calls each:

| Model | JSON mode | Valid | Latency | Completion tokens |
|---|---|---|---|---|
| `openai/gpt-oss-120b` | off | 3/3 | 1.3 s | 337 |
| `openai/gpt-oss-120b` | on | 3/3 | 0.9 s | 296 |
| `llama-3.3-70b-versatile` | either | — | — | 404 from the API |

`llama-3.3-70b-versatile` is not on this account. The models it can reach are `gpt-oss-120b`,
`gpt-oss-20b`, `gpt-oss-safeguard-20b` and `qwen/qwen3.8-27b`.

## Decision

Ask for `response_format: {"type": "json_object"}` on every structured call, on providers that
accept it. A provider that rejects the parameter has it dropped and is asked plainly from then
on, so nothing depends on the feature existing.

Keep a separate `GROQ_STRUCTURED_MODEL` setting, defaulting to the same model as free text
because that is what the measurement supports. It exists so the two can diverge without a code
change on an account whose model list differs.

Parse defensively regardless: strip markdown fences, skip any prose or reasoning before the
first brace, and read the first balanced object rather than slicing to the last brace, which a
trailing sentence would break. A real reply in `tests/fixtures/llm/groq/` opens with
`**Thinking**`, so this is not hypothetical.

Raise the output budget for write-ups and run summaries to `LLM_MAX_OUTPUT_TOKENS_REPORT`
(2,048). A reply cut off at the limit is recognisable now: the provider's finish reason is
recorded on the trace step, and the retry prompt quotes it along with the field that failed.

## Consequences

Structured calls are a little faster and cheaper on Groq. A validation failure is now readable
in the Traces screen instead of inferred: the step carries the raw reply, the finish reason,
the attempt number and the exact validation error, and the incident screen shows the last one
instead of saying only that something failed.

The fixtures under `tests/fixtures/llm/groq/` are real replies, captured from the account the
demo runs on: one plain object, one from JSON mode, one wrapped in prose and a markdown fence,
and one cut off at the token limit.
