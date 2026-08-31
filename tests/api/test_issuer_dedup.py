"""検索と今週の注目が同一発行体を二重に出さない（画面の 13010 / 15600）。"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from packages.core.storage import DuckDBRepo, SQLiteRepo, mark_live_ingest
from services.api.main import create_app


BEAR = "バリュートラップと業績モメンタム剥落の両方を却下理由として残す。"


def _security(ticker: str, name: str, *, valid_from: dt.date, sector: str = "その他") -> dict:
    return {
        "ticker": ticker,
        "market": "JP",
        "name_local": name,
        "sector_name": sector,
        "currency": "JPY",
        "valid_from": valid_from,
        "is_active": True,
    }


def _rec(rec_id: str, ticker: str, *, as_of: dt.date, horizon: str = "H20") -> dict:
    return {
        "rec_id": rec_id,
        "as_of": as_of,
        "ticker": ticker,
        "market": "JP",
        "action": "watch",
        "horizon": horizon,
        "conviction": "low",
        "conviction_score": 0.4,
        "thesis_ja": "定量スコア上位で注目する銘柄である。",
        "bear_case_ja": BEAR,
        "invalidation_ja": "次期予想が下方修正されたら破棄する。",
        "reason_codes": ["VAL_CHEAP_VS_SECTOR"],
        "citations": [
            {"doc_id": "quant:scores_daily", "quote": "定量スコアとML予測区間に基づく自動生成カードです。"}
        ],
        "source_doc_ids": ["quant:scores_daily"],
        "expected_ret": 0.02,
        "expected_ret_lo": -0.05,
        "expected_ret_hi": 0.08,
        "n_prior_samples": 8,
        "hit_rate_prior": 0.5,
    }


def _client() -> TestClient:
    duck = DuckDBRepo.in_memory()
    duck.init_db()
    sqlite = SQLiteRepo.in_memory()
    sqlite.init_db()
    duck.upsert_securities(
        [
            _security("14500", "TANAKEN", valid_from=dt.date(2026, 8, 1), sector="建設業"),
            _security(
                "15600",
                "野村アセットマネジメント株式会社 NEXT FUNDS FTSEブルサ・マレーシアKLCI連動型上場投信",
                valid_from=dt.date(2026, 8, 18),
            ),
            _security(
                "15600",
                "野村アセットマネジメント株式会社 NEXT FUNDS FTSEブルサ・マレーシアKLCI連動型上場投信",
                valid_from=dt.date(2026, 8, 25),
            ),
            _security("13010", "極洋", valid_from=dt.date(2026, 8, 18), sector="水産・農林業"),
            _security("13010", "極洋", valid_from=dt.date(2026, 8, 25), sector="水産・農林業"),
        ]
    )
    duck.insert_recommendation(_rec("rec-13010-a", "13010", as_of=dt.date(2026, 8, 31)))
    duck.insert_recommendation(_rec("rec-13010-b", "13010", as_of=dt.date(2026, 8, 31)))
    duck.insert_recommendation(_rec("rec-13010-old", "13010", as_of=dt.date(2026, 8, 28)))
    duck.insert_recommendation(_rec("rec-15600", "15600", as_of=dt.date(2026, 8, 31)))
    mark_live_ingest(sqlite, rows=1)
    app = create_app(duck=duck, sqlite=sqlite, payload={})
    return TestClient(app)


def test_search_極_returns_kyokuyo_once() -> None:
    with _client() as client:
        body = client.get("/api/v1/stocks/search", params={"q": "極", "limit": 10}).json()
        tickers = [item["ticker"] for item in body["data"]["items"]]
        assert tickers.count("13010") == 1
        assert "15600" not in tickers


def test_search_same_five_digit_code_once() -> None:
    with _client() as client:
        body = client.get("/api/v1/stocks/search", params={"q": "15600", "limit": 10}).json()
        tickers = [item["ticker"] for item in body["data"]["items"]]
        assert tickers == ["15600"]


def test_dashboard_highlights_one_card_per_issuer() -> None:
    with _client() as client:
        body = client.get("/api/v1/dashboard", params={"market": "JP"}).json()
        recs = body["data"]["top_recommendations"]
        tickers = [row["ticker"] for row in recs]
        assert tickers.count("13010") == 1
        assert len(tickers) == len(set(tickers))


def test_recommendations_latest_day_one_per_issuer_horizon() -> None:
    with _client() as client:
        body = client.get("/api/v1/recommendations", params={"market": "JP"}).json()
        keys = [(row["ticker"], row["horizon"], str(row["as_of"])) for row in body["data"]["items"]]
        assert len(keys) == len(set(keys))
        assert all(str(as_of).startswith("2026-08-31") for _, _, as_of in keys)
        assert sum(1 for ticker, _, _ in keys if ticker == "13010") == 1
