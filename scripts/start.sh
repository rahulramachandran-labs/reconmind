#!/bin/sh
# Container entrypoint: migrate, optionally load the seeded sample, then serve.
set -e
if [ -n "$DATABASE_URL" ]; then
  alembic upgrade head
  if [ "${SEED_SAMPLE:-false}" = "true" ]; then
    python -m app.pipeline.seed
  fi
fi
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"
