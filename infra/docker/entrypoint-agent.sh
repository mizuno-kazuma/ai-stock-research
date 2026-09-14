#!/usr/bin/env bash
set -euo pipefail

export PYTHONUTF8=1
export PYTHONUNBUFFERED=1
export DATA_DIR="${DATA_DIR:-/data}"

mkdir -p "$DATA_DIR"

echo "[entrypoint] standalone agent scheduler"
echo "[entrypoint] NOTE: DuckDB は単一ライタです。API と同時起動しないでください。"
exec uv run python -m services.agent.main
