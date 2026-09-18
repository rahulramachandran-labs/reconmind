# Architecture decision records

One file per decision that would be expensive to reverse, or that someone will ask "why" about. Each covers the context, the decision and the consequences. Superseded records stay, with a pointer to what replaced them.

| # | Decision | Status |
|---|---|---|
| [0001](0001-chunk-by-markdown-section.md) | Chunk by markdown section, then by size | accepted |
| [0002](0002-hybrid-retrieval-with-rrf.md) | Hybrid retrieval: BM25 and dense, fused with RRF | accepted |
| [0003](0003-onnx-embeddings-in-the-container.md) | Same embedding model, onnxruntime in the container | accepted |
| [0004](0004-append-only-ledger-in-postgres.md) | Postgres, with an append-only audit ledger enforced by a trigger | accepted |
| [0005](0005-provider-fallback-chain.md) | LLM provider fallback chain, with an extractive floor | accepted |
| [0006](0006-offline-eval-judges.md) | RAGAS gate with offline judges in CI | accepted |
