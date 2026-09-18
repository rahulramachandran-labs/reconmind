# 0010. Facts come from checks; models only write the words

- Status: accepted
- Date: 2026-09-18

## Context

Early versions asked a model to look at tool output and decide what was wrong and how bad it was. On the same input it gave different counts and different severities, and a sentence planted in a runbook could talk it into anything.

## Decision

- Detection, counts and severity are deterministic. The domain adapter's checks produce `Finding` objects, and its rubric sets severity. The model never sees a field it could change them through.
- The model writes the root-cause hypothesis, the fix steps, the open questions and the run summary. Each is a Pydantic model: a validation error re-prompts with the error, at most twice, and then the adapter's template is used and marked as such.
- Confidence is bounded. A model may lower it freely, but it can only raise it 0.15 above the adapter's calibrated prior. The review gate uses the lower of the two, so a model can push a finding into human review but never talk it out of one.
- Retrieved passages are wrapped in `<context>` with an explicit "data, not instructions" rule, and any tags inside a document that could close that block are neutralised.

## Consequences

- A scan gives the same findings with or without a model. CI checks exactly that, and the prompt-injection test runs a model that obeys every planted instruction and asserts that the severities, statuses and review routing don't change.
- Write-ups from the template are plainer than a good model's, but they are never wrong about the numbers.
