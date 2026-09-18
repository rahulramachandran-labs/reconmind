SHELL := /bin/bash
.DEFAULT_GOAL := help

API_PORT ?= 8000
WEB_PORT ?= 3000

.PHONY: help bootstrap dev api web test test-fast lint fmt eval index deck sync deploy clean

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

bootstrap: ## install python + node deps, git hooks, and a local .env
	uv sync
	cd frontend && npm ci
	uv run pre-commit install
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example")

dev: ## run api and web together (ctrl-c stops both)
	@trap 'kill 0' EXIT; \
	$(MAKE) --no-print-directory api & \
	$(MAKE) --no-print-directory web & \
	wait

api: ## run the api with reload
	uv run uvicorn app.main:app --reload --port $(API_PORT)

web: ## run the next.js dev server
	cd frontend && NEXT_PUBLIC_API_URL=http://localhost:$(API_PORT) npm run dev -- --port $(WEB_PORT)

test: ## full test suite with coverage gate
	uv run pytest --cov --cov-report=term

test-fast: ## skip tests that load the embedding model
	uv run pytest -m "not model" -q

lint: ## ruff, black --check, mypy, eslint
	uv run ruff check .
	uv run black --check .
	uv run mypy
	cd frontend && npm run lint

fmt: ## format python
	uv run ruff check . --fix
	uv run black .

index: ## build the dense index into .index/
	uv run python -c "from app.config import Settings; from app.retrieval.service import RetrievalService; s = RetrievalService.from_settings(Settings()); print(len(s.chunks), 'chunks indexed')"

deck: ## re-export the slide deck to pdf and refresh the cover image
	./docs/slides/export.sh

sync: ## hooks + tests, then commit everything and push. usage: make sync MSG="feat(x): ..."
	@test -n "$(MSG)" || (echo 'usage: make sync MSG="type(scope): message"'; exit 1)
	uv run pre-commit run --all-files || uv run pre-commit run --all-files
	$(MAKE) --no-print-directory test
	git add -A
	git commit -m "$(MSG)"
	git push origin main

deploy: ## deploy the web app to vercel (the api redeploys on push via render)
	cd frontend && vercel deploy --prod --yes

clean:
	rm -rf .index .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml frontend/.next
