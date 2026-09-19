# 0005. LLM provider fallback chain, with an extractive floor

- Status: accepted
- Date: 2026-09-18

## Context

The demo has to run at zero cost, on a laptop with no keys, in CI with no network model, and on a free hosted tier with no GPU. It should also use a better model when one is available, and survive a provider having a bad hour.

## Decision

- One `LLMChain` tries providers in order: OpenAI, Anthropic, local Ollama (through its OpenAI-compatible endpoint). Providers without credentials aren't built at all.
- A provider that throws is benched for 60 seconds, so an outage doesn't add a timeout to every request.
- `DEMO_MODE=true` removes the paid providers entirely.
- Every response carries the provider, model, token counts, estimated cost and the list of providers that failed before it.
- If nothing answers, the RAG path returns an extractive answer: the most relevant retrieved sentences, with citations, labelled as extractive.

## Consequences

- CI and the free hosted tier exercise the full retrieval path deterministically. The eval gate measures retrieval and grounding rather than whichever model happened to be reachable.
- Answer quality depends on which provider served the request, so the provider is always visible in the UI and the traces.
- The extractive floor is honest but blunt. It is a fallback, not a feature to tune.

## Update, 1.1

The free tiers of Groq, Google Gemini and OpenRouter now sit after OpenAI and Anthropic and before Ollama. They speak the OpenAI-compatible API, so they share one provider class; a 429 is retried before the chain moves on, and at most `LLM_CONCURRENCY` calls run at once to stay under a per-minute token limit.
