"""T-API-01: スキーマ / OpenAPI の経路が docs/09-api-spec.md と一致すること。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.api.main import create_app

REQUIRED_PATHS = {
    "/health",
    "/api/v1/dashboard",
    "/api/v1/recommendations",
    "/api/v1/recommendations/{rec_id}",
    "/api/v1/recommendations/{rec_id}/outcome",
    "/api/v1/recommendations/{rec_id}/feedback",
    "/api/v1/scores",
    "/api/v1/screener",
    "/api/v1/screener/presets",
    "/api/v1/screener/saved",
    "/api/v1/screener/saved/{saved_id}",
    "/api/v1/stocks/search",
    "/api/v1/stocks/{market}/{ticker}",
    "/api/v1/stocks/{market}/{ticker}/prices",
    "/api/v1/stocks/{market}/{ticker}/financials",
    "/api/v1/stocks/{market}/{ticker}/features",
    "/api/v1/stocks/{market}/{ticker}/documents",
    "/api/v1/stocks/{market}/{ticker}/recommendations",
    "/api/v1/stocks/{market}/{ticker}/peers",
    "/api/v1/documents",
    "/api/v1/documents/{doc_id}",
    "/api/v1/documents/{doc_id}/file",
    "/api/v1/documents/{doc_id}/summary",
    "/api/v1/documents/{doc_id}/chunks",
    "/api/v1/fx/{pair}",
    "/api/v1/fx/{pair}/history",
    "/api/v1/macro/series",
    "/api/v1/macro/rate-differential",
    "/api/v1/models/runs",
    "/api/v1/models/runs/{run_id}",
    "/api/v1/models/runs/{run_id}/feature-importance",
    "/api/v1/models/runs/{run_id}/ic-timeseries",
    "/api/v1/models/health",
    "/api/v1/backtests",
    "/api/v1/backtests/{backtest_id}",
    "/api/v1/backtests/{backtest_id}/equity-curve",
    "/api/v1/backtests/{backtest_id}/trades",
    "/api/v1/factor-weights",
    "/api/v1/factor-weights/{weight_set_id}/activate",
    "/api/v1/agent/jobs",
    "/api/v1/agent/jobs/{job_run_id}",
    "/api/v1/agent/jobs/{job_name}/run",
    "/api/v1/agent/jobs/{job_run_id}/cancel",
    "/api/v1/agent/memory",
    "/api/v1/agent/memory/{memory_id}",
    "/api/v1/agent/cost",
    "/api/v1/agent/critic-stats",
    "/api/v1/agent/events",
    "/api/v1/portfolio",
    "/api/v1/portfolio/positions",
    "/api/v1/portfolio/performance",
    "/api/v1/trades",
    "/api/v1/trades/{trade_id}",
    "/api/v1/trades/import",
    "/api/v1/trades/analysis",
    "/api/v1/watchlist",
    "/api/v1/watchlist/{market}/{ticker}",
    "/api/v1/settings",
    "/api/v1/alerts",
    "/api/v1/alerts/{alert_id}/read",
    "/api/v1/alerts/read-all",
    "/api/v1/system/health",
    "/api/v1/system/freshness",
    "/api/v1/system/backup",
}


def test_openapi_contains_all_spec_paths() -> None:
    app = create_app()
    spec = app.openapi()
    paths = set(spec["paths"])
    missing = sorted(p for p in REQUIRED_PATHS if p not in paths)
    assert not missing, f"OpenAPI に無い仕様パス: {missing}"


def test_openapi_json_endpoint(client: TestClient) -> None:
    r = client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    body = r.json()
    assert "paths" in body
    assert "/api/v1/dashboard" in body["paths"]


def test_generated_ts_types_match_openapi() -> None:
    """T-API-01: OpenAPI から再生成した TS 型がコミット済み生成物と一致すること。"""
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts" / "gen_api_types.py"
    subprocess.check_call([sys.executable, str(script), "--check"])
