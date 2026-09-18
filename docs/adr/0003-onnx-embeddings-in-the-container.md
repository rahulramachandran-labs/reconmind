# 0003. Same embedding model, onnxruntime in the container

- Status: accepted
- Date: 2026-09-18

## Context

The API is meant to run on a 512 MB instance. With sentence-transformers the Phase A image idled at 361 MB and reached 448 MB after the first query, almost all of it torch. Agents, MCP clients and tracing still had to fit on top.

## Decision

Keep `sentence-transformers/all-MiniLM-L6-v2` everywhere, but run it through `fastembed` (onnxruntime) inside the container. torch, transformers and sentence-transformers move into a `local-models` dependency group that is installed by default for development and CI, and left out of the image. `EMBEDDINGS_BACKEND=fastembed` is set in the Dockerfile.

## Consequences

- The image drops torch entirely. Both backends load the same weights, so vectors agree to within float noise and nothing downstream changes.
- Two code paths for embeddings. The fastembed one is a thin class with its own test; the retrieval tests don't care which backend produced the vectors.
- Cross-encoder judges for evaluation still need torch, which is fine: evals never run in the container.
