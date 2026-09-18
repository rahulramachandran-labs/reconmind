# 0006. RAGAS gate with offline judges in CI

- Status: accepted
- Date: 2026-09-18

## Context

RAGAS's headline metrics (faithfulness, answer relevancy, LLM context precision and recall) need an LLM judge. CI has no API key, and a small local model as judge was both slow on CI runners and noisy in its JSON output.

## Decision

`evals/run_ragas.py` has two judges.

- **offline**, used in CI and by default:
  - Context precision and recall use RAGAS's own non-LLM metrics (`NonLLMContextPrecisionWithReference`, `NonLLMContextRecall`). The golden set lists the exact reference chunks, so the similarity threshold is 0.9.
  - Faithfulness is the share of answer sentences entailed by some window of a retrieved passage, scored with an NLI cross-encoder (`cross-encoder/nli-MiniLM2-L6-H768`). Passages are cut into two-sentence windows because NLI models are trained on short premises. Scoring against whole chunks under-counted support by half.
  - Answer relevancy is the MS MARCO cross-encoder score of the answer against the question.
- **llm**, with `--judge llm`: the LLM-judged RAGAS metrics, using OpenAI when a key is present and Ollama otherwise.

Every run records the judge, the retriever and which provider produced the answers in `evals/history.csv`.

## Consequences

- The CI gate is deterministic and free, and a regression in retrieval or grounding fails the build.
- Offline and LLM scores are not the same numbers and are never mixed in the history.
- In CI the answers are extractive, so the gate mostly measures retrieval. Generated-answer quality gets measured with `--judge llm` when a model is available.
