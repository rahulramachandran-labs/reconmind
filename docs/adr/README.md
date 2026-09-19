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
| [0007](0007-langgraph-over-crewai.md) | LangGraph over CrewAI for orchestration | accepted |
| [0008](0008-mcp-over-direct-clients.md) | Agents reach the pipeline through MCP, not direct clients | accepted |
| [0009](0009-tracing-langfuse-and-postgres.md) | Trace every step to Postgres, mirror to LangFuse | accepted |
| [0010](0010-facts-from-checks-language-from-models.md) | Facts come from checks; models only write the words | accepted |
| [0011](0011-scheduled-scans-and-finding-fingerprints.md) | Scheduled scans from outside the API; findings are fingerprinted | accepted |
