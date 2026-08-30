"""シードと本番データの分離（F02）。

空倉庫では sample-data.json を出してよい。Collector が live 価格を
upsert したあとは、シードカードを本番として返さない。
"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from packages.core.storage import (
    DuckDBRepo,
    LIVE_DATA_KEY,
    SEED_DATA_KEY,
    SQLiteRepo,
    is_serving_seed,
    mark_live_ingest,
)
from services.agent.jobs.collector import COLLECTOR_STEPS, collector
from services.agent.jobs.strategist import build_recommendation
from services.api.main import create_app
from services.api.seed import load_sample
from tests.fakes import FakeStateRepo, FakeWarehouse


SEED_REC_ID = "01J8XKQ3M4N5P6R7S8T9V0W1X2"
LIVE_REC_ID = "live-rec-7203-h20"


def _live_recommendation() -> dict:
    import pandas as pd

    row = pd.Series(
        {
            "ticker": "7203",
            "quant_score": 70,
            "total_score": 70,
            "ml_pred_h20": 0.03,
            "ml_pred_h20_lo": -0.02,
            "ml_pred_h20_hi": 0.07,
            "reason_codes": ["VAL_CHEAP_VS_SECTOR"],
        }
    )
    rec = build_recommendation(
        row,
        as_of=dt.date(2026, 8, 28),
        market="JP",
        n_prior_samples=8,
        hit_rate_prior=None,
        thesis=None,
        memory_ids=[],
        source_doc_ids=["quant:scores_daily"],
        data_freshness=[],
    )
    rec["rec_id"] = LIVE_REC_ID
    return rec


def test_seed_flag_stays_true_when_warehouse_is_empty_and_seeded(client: TestClient) -> None:
    r = client.get("/api/v1/recommendations")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["is_seed_data"] is True
    codes = {w["code"] for w in body["warnings"]}
    assert "SEED_DATA" in codes
    rec_ids = {item["rec_id"] for item in body["data"]["items"]}
    assert SEED_REC_ID in rec_ids


def test_api_does_not_serve_seed_cards_after_live_ingest() -> None:
    duck = DuckDBRepo.in_memory()
    duck.init_db()
    sqlite = SQLiteRepo.in_memory()
    sqlite.init_db()
    payload = load_sample()
    sqlite.set_setting(SEED_DATA_KEY, True)
    app = create_app(duck=duck, sqlite=sqlite, payload=payload)
    with TestClient(app) as client:
        before = client.get("/api/v1/recommendations")
        assert before.status_code == 200
        assert before.json()["meta"]["is_seed_data"] is True
        seed_ids = {item["rec_id"] for item in before.json()["data"]["items"]}
        assert SEED_REC_ID in seed_ids

        duck.upsert_prices_daily(
            [
                {
                    "ticker": "7203",
                    "market": "JP",
                    "trade_date": dt.date(2026, 8, 28),
                    "open": 3000.0,
                    "high": 3050.0,
                    "low": 2980.0,
                    "close": 3020.0,
                    "volume": 1_000_000,
                    "adj_close": 3020.0,
                    "currency": "JPY",
                    "source": "jquants",
                }
            ]
        )
        duck.insert_recommendation(_live_recommendation())
        mark_live_ingest(sqlite, rows=1)

        after = client.get("/api/v1/recommendations")
        assert after.status_code == 200
        body = after.json()
        assert body["meta"]["is_seed_data"] is False
        codes = {w["code"] for w in body["warnings"]}
        assert "SEED_DATA" not in codes
        rec_ids = {item["rec_id"] for item in body["data"]["items"]}
        assert rec_ids == {LIVE_REC_ID}
        assert SEED_REC_ID not in rec_ids

        missing = client.get(f"/api/v1/recommendations/{SEED_REC_ID}")
        assert missing.status_code == 404


def test_freshness_comes_from_duckdb_after_live_ingest() -> None:
    duck = DuckDBRepo.in_memory()
    duck.init_db()
    sqlite = SQLiteRepo.in_memory()
    sqlite.init_db()
    payload = load_sample()
    sqlite.set_setting(SEED_DATA_KEY, True)
    duck.upsert_prices_daily(
        [
            {
                "ticker": "7203",
                "market": "JP",
                "trade_date": dt.date(2026, 8, 28),
                "open": 3000.0,
                "high": 3050.0,
                "low": 2980.0,
                "close": 3020.0,
                "volume": 1_000_000,
                "adj_close": 3020.0,
                "currency": "JPY",
                "source": "jquants",
            }
        ]
    )
    mark_live_ingest(sqlite, rows=1)
    app = create_app(duck=duck, sqlite=sqlite, payload=payload)
    with TestClient(app) as client:
        r = client.get("/api/v1/system/freshness")
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["is_seed_data"] is False
        sources = {row["source"]: row.get("latest_as_of") for row in body["data"]["sources"]}
        assert "yfinance_jp" not in sources
        assert "yfinance_us" not in sources
        assert "sec_edgar" not in sources
        assert "jquants" in sources
        assert str(sources["jquants"]).startswith("2026-08-28")
        duck_view = duck.data_freshness()
        assert duck_view.get("jquants") == dt.date(2026, 8, 28)


def test_collector_clears_seed_flag_after_live_prices() -> None:
    state = FakeStateRepo()
    state.set_setting(SEED_DATA_KEY, True)
    warehouse = FakeWarehouse()
    steps = {name: (lambda m, a: {"skipped": True}) for name, _req in COLLECTOR_STEPS}
    steps["prices"] = lambda market, as_of: {"rows": 12, "batches": 1}
    result = collector(
        "JP",
        dt.date(2026, 8, 28),
        state=state,
        warehouse=warehouse,
        steps=steps,
    )
    assert result.status == "success"
    assert result.metrics.get("cleared_seed_data") is True
    assert is_serving_seed(state) is False
    assert state.get_setting(LIVE_DATA_KEY) is True
    assert state.get_setting(SEED_DATA_KEY) is False


def test_collector_keeps_seed_when_prices_skipped() -> None:
    state = FakeStateRepo()
    state.set_setting(SEED_DATA_KEY, True)
    warehouse = FakeWarehouse()
    steps = {name: (lambda m, a: {"skipped": True}) for name, _req in COLLECTOR_STEPS}
    steps["prices"] = lambda market, as_of: {"skipped": True, "reason": "watchlist empty", "rows": 0}
    result = collector(
        "US",
        dt.date(2026, 8, 28),
        state=state,
        warehouse=warehouse,
        steps=steps,
    )
    assert result.steps["prices"].status == "success"
    assert result.metrics.get("cleared_seed_data") is None
    assert is_serving_seed(state) is True
