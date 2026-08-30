#!/bin/sh
set -e

echo "[entrypoint] ensuring data dirs..."
mkdir -p /app/data/adversarial_buffer /app/data/evaluation

# If a volume wiped baked buffer, restore from image seed copy when present.
if [ ! -s /app/data/adversarial_buffer/evidence.jsonl ] && [ -s /app/seed/adversarial_buffer/evidence.jsonl ]; then
  echo "[entrypoint] restoring evidence.jsonl from image seed"
  cp -a /app/seed/adversarial_buffer/. /app/data/adversarial_buffer/
fi

if [ ! -f /app/data/platform.db ] && [ -f /app/seed/platform.db ]; then
  echo "[entrypoint] restoring platform.db from image seed"
  cp -a /app/seed/platform.db /app/data/platform.db
fi

echo "[entrypoint] seeding Postgres from demo SQLite (if empty)..."
cd /app
PYTHONPATH=/app python /app/scripts/seed_demo_to_pg.py || echo "[entrypoint] seed skipped/failed (non-fatal)"

echo "[entrypoint] starting API..."
exec python -m uvicorn backend.api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 1 \
  --log-level info \
  --access-log
