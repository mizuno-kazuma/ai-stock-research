#!/usr/bin/env bash
set -euo pipefail

export PYTHONUTF8=1
export PYTHONUNBUFFERED=1
export DATA_DIR="${DATA_DIR:-/data}"
export PATH="/app/.venv/bin:${PATH}"

mkdir -p "$DATA_DIR"

echo "[entrypoint] ensuring directories and state DB schema..."
python -m packages.core.storage.init_db

echo "[entrypoint] starting API (embedded agent scheduler) on ${API_HOST:-0.0.0.0}:${API_PORT:-8000}"
exec uvicorn services.api.main:app \
  --host "${API_HOST:-0.0.0.0}" \
  --port "${API_PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
