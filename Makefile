# AI Stock Research — ルート Makefile
# 改行は LF。Windows では Git Bash / WSL の `make`、または README の PowerShell 手順を使う。

export PYTHONUTF8 := 1
export PYTHONIOENCODING := utf-8

.PHONY: sync init-db seed test api openapi gen-api check-api

sync:
	uv sync

init-db:
	uv run python -m packages.core.storage.init_db

seed:
	uv run python -m services.api.seed

test:
	uv run pytest

api:
	uv run uvicorn services.api.main:app --host 0.0.0.0 --port 8000

openapi:
	uv run python -m services.api.export_openapi

gen-api:
	uv run python scripts/gen_api_types.py

check-api:
	uv run python scripts/gen_api_types.py --check

.PHONY: cloud-init-db docker-api docker-web compose-cloud
cloud-init-db:
	uv run python scripts/cloud_init_db.py

docker-api:
	docker build -f infra/docker/Dockerfile.api -t ai-stock-api:local .

docker-web:
	docker build -f infra/docker/Dockerfile.web -t ai-stock-web:local .

compose-cloud:
	docker compose -f docker-compose.cloud.yml up --build
