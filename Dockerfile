FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    HF_HOME=/opt/hf \
    OMP_NUM_THREADS=1 \
    TOKENIZERS_PARALLELISM=false \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

WORKDIR /app
RUN useradd --create-home --uid 10001 app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY corpus ./corpus
RUN uv sync --frozen --no-dev

# Download the embedding model and build the index at image build time so a
# cold start on a small instance doesn't spend a minute fetching weights.
RUN python -c "from app.config import Settings; from app.retrieval.service import RetrievalService; RetrievalService.from_settings(Settings())" \
    && chown -R app:app /app /opt/hf

USER app
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
