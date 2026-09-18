FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/opt/hf \
    FASTEMBED_CACHE_PATH=/opt/hf/fastembed \
    OMP_NUM_THREADS=1 \
    TOKENIZERS_PARALLELISM=false \
    EMBEDDINGS_BACKEND=fastembed \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app
RUN useradd --create-home --uid 10001 app

# no torch in the image: embeddings run on onnxruntime (see ADR 0003)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-default-groups --group onnx --no-install-project

COPY app ./app
COPY corpus ./corpus
COPY dbt ./dbt
COPY data ./data
COPY migrations ./migrations
COPY alembic.ini ./
COPY scripts/start.sh ./scripts/start.sh
RUN uv sync --frozen --no-default-groups --group onnx

# fetch the embedding model and build the index at build time so a cold start
# on a small instance doesn't spend a minute downloading weights
RUN python -c "from app.config import Settings; from app.retrieval.service import RetrievalService; RetrievalService.from_settings(Settings())" \
    && chown -R app:app /app /opt/hf

USER app
EXPOSE 8000
CMD ["./scripts/start.sh"]
