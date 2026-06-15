#!/bin/sh
set -e

# Si arrancamos como root (los bind mounts vienen montados como root),
# corregimos permisos de las carpetas escribibles y bajamos a 'app'.
if [ "$(id -u)" = "0" ]; then
    chown -R app:app /app/logs /app/pdfs /app/.afip_cache /app/certs
    exec gosu app "$0" "$@"
fi

# --- de acá para abajo ya corremos como 'app' ---
echo "[entrypoint] init_db.py (idempotente: tablas + admin)..."
python scripts/init_db.py

echo "[entrypoint] Levantando uvicorn..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --proxy-headers \
    --forwarded-allow-ips "*" \
    --workers "${UVICORN_WORKERS:-2}"
