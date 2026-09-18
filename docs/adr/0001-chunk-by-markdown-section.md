# 0001. Chunk by markdown section, then by size

- Status: accepted
- Date: 2026-09-18

## Context

The corpus is runbooks, schema docs and incident write-ups. They are short (1-3 KB), heavily sectioned (`Detection`, `Fix`, `Severity`), and the sections are what people actually ask about. A question like "what's the fix for key drift" should land on the Fix section of the key-drift runbook, not on a fixed-size window that straddles Detection and Fix.

Fixed-size chunking was the first thing tried. It produced chunks that started mid-table and chunks where the fix for one problem sat next to the detection query for another, which confused both retrieval and the answer.

## Decision

1. Split each document on `#`, `##`, `###` with LangChain's `MarkdownHeaderTextSplitter`.
2. Split any section longer than 900 characters with `RecursiveCharacterTextSplitter`, 120 characters of overlap.
3. Prefix every chunk with `"{document title} | {section path}"` before embedding.
4. Chunk ids are `{doc_id}#{section-slug}-{n}` so they are stable across rebuilds and readable in logs and eval files.

## Consequences

- A section called "Fix" still carries what it is fixing, which matters for both the dense and (later) keyword side of retrieval.
- Chunks are small (about 350 characters on average), so `k=5` fits comfortably in a small local model's context.
- Several chunks from the same document can crowd the top results. For questions about a single incident that turned out to be what you want (see [0002](0002-hybrid-retrieval-with-rrf.md)).
- Tables are kept whole inside a section, which the severity rubric depends on.
