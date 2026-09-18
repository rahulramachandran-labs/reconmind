# Changelog

All notable changes, grouped by build phase. Dates are UTC.

## [Unreleased]

## [phase-a] - 2026-09-18

### Added
- Synthetic knowledge corpus: nine runbooks, five schema docs, five past incident write-ups.
- Markdown-aware chunking (section first, then size) with title and section carried into every chunk.
- Dense retrieval with sentence-transformers `all-MiniLM-L6-v2` and FAISS, cached on disk by corpus fingerprint.
- Single OpenAI-compatible LLM client (OpenAI or Ollama) with an extractive fallback when no model is reachable.
- FastAPI: `/healthz`, `/ask`, `/search`, `/corpus`.
- Next.js + shadcn/ui page for asking questions with cited sources.
- CI: ruff, black, mypy, pytest with an 80% coverage gate, gitleaks over full history, `next build`.
- Pre-commit hooks, Makefile, Dockerfile, Render blueprint and Railway config.
- Project deck (PPTX, PDF export, cover image) under `docs/slides`, with `make deck` to re-export.
