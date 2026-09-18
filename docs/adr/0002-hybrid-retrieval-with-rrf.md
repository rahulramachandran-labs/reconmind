# 0002. Hybrid retrieval: BM25 and dense, fused with RRF

- Status: accepted
- Date: 2026-09-18

## Context

The Phase A retriever was dense only (MiniLM on FAISS). It handled paraphrased questions well and identifiers badly. "basket_ref ContractViolation" returned the transactions schema doc three times and missed both the schema-drift runbook and the incident where exactly that happened. Runbooks in this domain are full of exact tokens (column names, error names, file patterns, outlet ids) that embeddings blur together.

## Decision

- Run BM25 (`rank_bm25`) and dense search side by side, 20 candidates each, and merge them with reciprocal rank fusion, `score = Σ 1 / (60 + rank)`. RRF only looks at ranks, so BM25 scores and cosine similarities never have to be calibrated against each other.
- Tokenize for BM25 so identifiers survive: `channel_basket_id` is indexed whole and as its stemmed parts; plain words go through a Snowball stemmer.
- BM25 `k1=1.2, b=0.5`. Chunks that carry a table are long for a reason, so length is penalised less than the textbook `b=0.75`.
- Wrap it as a LangChain `BaseRetriever` so it drops into chains, and keep `dense` and `bm25` selectable for comparison.

## Evidence

Golden set, 46 questions, extractive answers, offline judges, k=5:

| retriever | context precision | context recall |
|---|---|---|
| dense (Phase A) | 0.661 | 0.844 |
| hybrid | 0.756 | 0.911 |

Things that were tried and dropped:

- **A per-document cap of two chunks.** Its purpose was to stop one document crowding the results. It cost eight points of recall, because questions about one incident legitimately need several of its sections. It is still a parameter, but off by default.
- **Weighting dense above BM25, or the reverse.** Within noise on this set, so both lists get equal weight.
- **Boosting section headings in BM25.** Also within noise.

## Addendum: reranking

A cross-encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) now reranks the fused top 10. On the same golden set, context precision went from 0.756 to 0.830 and recall from 0.911 to 0.922. Reranking the top 20 was no better than the top 10. Blending the reranker's rank with the fusion rank was worse than letting the reranker decide. The container runs the same weights through fastembed's ONNX cross-encoder, and `RERANKER=none` turns it off.

## Consequences

- One more index to build at startup. BM25 over ~90 chunks is instant.
- Reranking adds roughly 100 ms per query on CPU, which is noise next to a model call.
