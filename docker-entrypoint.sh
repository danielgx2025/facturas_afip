#!/bin/sh
set -e

echo "[entrypoint] init_db.py (idempotente: tablas + admin)..."
python scripts/init_db.py

echo "[entrypoint] Levantando uvicorn..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --proxy-headers \
    --forwarded-allow-ips "*" \
    --workers "${UVICORN_WORKERS:-2}"
