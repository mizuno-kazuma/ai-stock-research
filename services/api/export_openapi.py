"""OpenAPI JSON を標準出力へ出す（docs/12-testing-validation.md T-API-01）。

    uv run python -m services.api.export_openapi > openapi.json
"""

from __future__ import annotations

from packages.schemas.export import main

if __name__ == "__main__":
    raise SystemExit(main())
