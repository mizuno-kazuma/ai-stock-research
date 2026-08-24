"""T-API-02 / 契約: 200 JSON は Envelope（data / warnings / meta.data_freshness）。"""

from __future__ import annotations

from fastapi.testclient import TestClient

GET_PATHS = [
    "/api/v1/dashboard",
    "/api/v1/recommendations",
    "/api/v1/scores",
    "/api/v1/screener/presets",
    "/api/v1/screener/saved",
    "/api/v1/stocks/search?q=7203",
    "/api/v1/stocks/JP/7203",
    "/api/v1/stocks/JP/7203/prices",
    "/api/v1/stocks/JP/7203/financials",
    "/api/v1/stocks/JP/7203/features",
    "/api/v1/stocks/JP/7203/documents",
    "/api/v1/stocks/JP/7203/recommendations",
    "/api/v1/stocks/JP/7203/peers",
    "/api/v1/documents",
    "/api/v1/fx/USDJPY",
    "/api/v1/fx/USDJPY/history",
    "/api/v1/macro/series?ids=DGS10,DEXJPUS",
    "/api/v1/macro/rate-differential",
    "/api/v1/models/runs",
    "/api/v1/models/health",
    "/api/v1/backtests",
    "/api/v1/factor-weights",
    "/api/v1/agent/jobs",
    "/api/v1/agent/memory",
    "/api/v1/agent/cost",
    "/api/v1/agent/critic-stats",
    "/api/v1/portfolio",
    "/api/v1/portfolio/positions",
    "/api/v1/portfolio/performance",
    "/api/v1/trades",
    "/api/v1/trades/analysis",
    "/api/v1/watchlist",
    "/api/v1/settings",
    "/api/v1/alerts",
    "/api/v1/system/health",
    "/api/v1/system/freshness",
]


def test_all_endpoints_return_envelope(client: TestClient) -> None:
    for path in GET_PATHS:
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:300]}"
        ctype = r.headers.get("content-type", "")
        if not ctype.startswith("application/json"):
            continue
        body = r.json()
        assert set(body.keys()) >= {"data", "warnings", "meta"}, path
        assert "data_freshness" in body["meta"], path
        assert isinstance(body["warnings"], list), path
