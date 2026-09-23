# Baseline, before the hardening work

Captured on 2026-09-23 from `main` at `a148556`, so every later claim can be diffed against
something rather than asserted. Files here are raw output, not prose.

| What | Where | Result |
|---|---|---|
| Lint and types | [`lint.txt`](lint.txt) | ruff, black on 124 files, mypy on 79 source files, eslint: clean |
| Tests | [`tests.txt`](tests.txt) | 172 passed, 0 failed, 90.90% coverage against the 80% gate |
| Live API health | [`healthz.json`](healthz.json) | `status: ok`, version 1.1.0, 86 chunks, hybrid, `database: true`, providers groq and gemini |
| Live model | [`model.json`](model.json) | groq `openai/gpt-oss-120b`, chain groq then gemini |
| Environment as deployed | [`environment.md`](environment.md) | 16 variables on Render, 7 on Vercel, none of them new |
| Default image | built from [`Dockerfile`](../../../Dockerfile) | 584,290,755 bytes (557 MiB) on disk for `linux/arm64`, with the embedding model and the built index inside it |

The image number is disk size, not memory. What the free instance limits is RSS, and the reason
the reranker stays out of the image ([ADR 0003](../../adr/0003-onnx-embeddings-in-the-container.md))
is that it grows with use, not that it is large on disk. The hardening work must leave this number
where it is: anything needed only for observability goes in its own dependency group, behind a
build argument that is off by default.

`make test` reports 90.90% here and 92.58% in [`../tests.txt`](../tests.txt) because the capture run
has a database and a model to talk to, so it reaches code this run cannot.
