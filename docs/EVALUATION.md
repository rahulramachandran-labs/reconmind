# Evaluation

ReconMind is measured on two things: whether retrieval and answers are good (RAGAS on a golden set), and whether the agents catch what they should (tests that plant each problem and check it is found). Both run in CI on every push.

## Golden set and RAGAS

[`evals/golden_set.jsonl`](../evals/golden_set.jsonl) holds 46 question, answer and context triples covering every anomaly type and every screen. [`evals/run_ragas.py`](../evals/run_ragas.py) scores four metrics, CI fails if any drops below [`evals/thresholds.yaml`](../evals/thresholds.yaml), and each run appends a row to [`evals/history.csv`](../evals/history.csv).

| Metric | Question it answers | Threshold |
|---|---|---|
| Faithfulness | Is every claim in the answer supported by the retrieved passages? | 0.85 |
| Answer relevancy | Does the answer address the question? | 0.80 |
| Context precision | Are the relevant passages ranked near the top? | 0.80 |
| Context recall | Was everything needed to answer retrieved at all? | 0.85 |

**Judges.** CI has no API key, so it uses offline judges ([ADR 0006](adr/0006-offline-eval-judges.md)): RAGAS's non-LLM context precision and recall, an NLI cross-encoder for faithfulness (scored against two-sentence windows of each passage, since a whole passage mixes too many claims), and the 12-layer MS MARCO cross-encoder for relevancy, so the 6-layer reranker isn't grading its own output. `--judge llm` switches to RAGAS's LLM-judged metrics, using OpenAI or a local Ollama.

```bash
make eval                                                         # hybrid (default), gate and record
uv run --group eval python evals/run_ragas.py --retriever dense   # dense-only baseline
uv run --group eval python evals/run_ragas.py --judge llm       # LLM judges instead of offline ones
```

## Scores

Each row names who wrote the answers and who judged them, k = 5:

| Retriever | Answers written by | Judged by | Faithfulness | Answer relevancy | Context precision | Context recall | Gate |
|---|---|---|---|---|---|---|---|
| Dense only | extractive | offline | 0.920 | 0.863 | 0.661 | 0.844 | fail |
| Hybrid (BM25 + dense, RRF) | extractive | offline | 0.917 | 0.864 | 0.756 | 0.911 | fail |
| **Hybrid + cross-encoder rerank (default, the CI gate)** | **extractive** | **offline** | **0.911** | **0.862** | **0.830** | **0.922** | **pass** |
| Hybrid + cross-encoder rerank | `qwen2.5:1.5b` via Ollama | offline | 0.427 | 0.624 | 0.830 | 0.922 | fail |

The model row keeps retrieval identical, so context precision and recall don't move; only the answers change. A 1.5-billion-parameter local model paraphrases loosely and adds detail the passages don't support, and the NLI judge scores that as low faithfulness. That is why the gate runs on extractive answers, which can't claim more than the passages say, and why the hosted demo is set up for a larger model. To score another model, set its key and run `make eval`; add `--judge llm` for LLM judges.

Hybrid search is what moves precision and recall: pipeline questions are full of exact identifiers (`basket_ref`, `OUT-1071`, `validate_schema`) that embeddings blur and BM25 matches. The reranker then puts the best of the fused candidates first.

## Agent behaviour

| Test | What it proves |
|---|---|
| [`tests/chaos/`](../tests/chaos) | Plants each anomaly on its own with the generator, then checks the right specialist finds it with the right severity, and that a full investigation finishes inside the 30-second budget |
| [`test_agents.py`](../tests/integration/test_agents.py) | Routing, parallel specialists, the S1 pause and resume, confidence capping, repeated scans not duplicating findings |
| [`test_prompt_injection.py`](../tests/integration/test_prompt_injection.py) | A runbook carrying planted instructions can't change a severity or approve anything |
| [`test_domain_agnostic.py`](../tests/integration/test_domain_agnostic.py) | The same graph runs on the support-triage domain, and no agent module imports a domain |
| [`test_tracer.py`](../tests/unit/test_tracer.py), [`test_structured.py`](../tests/unit/test_structured.py) | Every step is traced; a model call outside a traced run is refused; invalid model output is retried, then replaced by the template |

## Quality bar

- RAGAS faithfulness ≥ 0.85, answer relevancy ≥ 0.80, context precision ≥ 0.80, context recall ≥ 0.85
- Every planted anomaly caught by the right agent at the right severity
- Test coverage ≥ 80% (currently 93%)
- A full investigation in under 30 seconds with no model
- Zero untraced model calls
