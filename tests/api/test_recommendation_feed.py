"""推奨一覧はスコア済みユニバースを母集団にし、既定表示は少なくとも10件出す。"""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from packages.core.storage import DuckDBRepo, SQLiteRepo, mark_live_ingest
from services.api.main import create_app

BEAR = "バリュートラップと業績モメンタム剥落の両方を却下理由として残す。"
DAY = dt.date(2026, 8, 31)


def _security(ticker: str, name: str, sector: str = "輸送用機器") -> dict:
    return {
        "ticker": ticker,
        "market": "JP",
        "name_local": name,
        "sector_name": sector,
        "currency": "JPY",
        "valid_from": dt.date(2026, 1, 1),
        "is_active": True,
    }


def _score(ticker: str, total: float, *, pred: float = 0.02) -> dict:
    return {
        "ticker": ticker,
        "market": "JP",
        "as_of": DAY,
        "weight_set_id": "default",
        "total_score": total,
        "quant_score": total,
        "ml_pred_h20": pred,
        "ml_pred_h20_lo": pred - 0.04,
        "ml_pred_h20_hi": pred + 0.04,
        "value_z": 1.2 if total >= 70 else 0.1,
    }


def _rec(
    rec_id: str,
    ticker: str,
    *,
    verdict: str | None = "approved",
    rank_fill: bool = False,
) -> dict:
    reasons = ["VAL_CHEAP_VS_SECTOR"]
    if rank_fill:
        reasons.append("RANK_FILL")
    return {
        "rec_id": rec_id,
        "as_of": DAY,
        "ticker": ticker,
        "market": "JP",
        "action": "watch",
        "horizon": "H20",
        "conviction": "low",
        "conviction_score": 0.4,
        "thesis_ja": "定量スコア上位で注目する銘柄である。",
        "bear_case_ja": BEAR,
        "invalidation_ja": "次期予想が下方修正されたら破棄する。",
        "reason_codes": reasons,
        "citations": [
            {"doc_id": "quant:scores_daily", "quote": "定量スコアとML予測区間に基づく自動生成カードです。"}
        ],
        "source_doc_ids": ["quant:scores_daily"],
        "expected_ret": 0.02,
        "expected_ret_lo": -0.05,
        "expected_ret_hi": 0.08,
        "n_prior_samples": 8,
        "hit_rate_prior": 0.5,
        "total_score": 80,
        "quant_score": 80,
        "critic_verdict": verdict,
    }


def _client(*, scores: list[dict], recs: list[dict], securities: list[dict]) -> TestClient:
    duck = DuckDBRepo.in_memory()
    duck.init_db()
    sqlite = SQLiteRepo.in_memory()
    sqlite.init_db()
    if securities:
        duck.upsert_securities(securities)
    if scores:
        duck.upsert_scores_daily(scores)
    for rec in recs:
        duck.insert_recommendation(rec)
    mark_live_ingest(sqlite, rows=1)
    app = create_app(duck=duck, sqlite=sqlite, payload={})
    return TestClient(app)


NAMES = {
    "7203": "トヨタ自動車",
    "6758": "ソニーグループ",
    "9984": "ソフトバンクグループ",
    "6861": "キーエンス",
    "4063": "信越化学工業",
    "9432": "日本電信電話",
    "8058": "三菱商事",
    "6098": "リクルートホールディングス",
    "7267": "本田技研工業",
    "6501": "日立製作所",
    "6273": "SMC",
    "8306": "三菱UFJフィナンシャル・グループ",
}


def test_universe_lists_scores_not_just_cards() -> None:
    tickers = list(NAMES)
    scores = [_score(t, 90 - i) for i, t in enumerate(tickers)]
    recs = [_rec("rec-7203", "7203", verdict="rejected")]
    secs = [_security(t, n) for t, n in NAMES.items()]
    with _client(scores=scores, recs=recs, securities=secs) as client:
        body = client.get("/api/v1/recommendations", params={"market": "JP"}).json()
        items = body["data"]["items"]
        assert body["data"]["universe_size"] == len(tickers)
        assert len(items) >= 10
        by_ticker = {row["ticker"]: row for row in items}
        assert by_ticker["7203"]["critic_verdict"] == "rejected"
        assert by_ticker["7203"]["name_local"] == "トヨタ自動車"
        score_only = [row for row in items if row["display_tier"] == "score_only"]
        assert len(score_only) >= 9
        for row in items:
            assert row["name_local"]
            assert row["name_local"] != row["ticker"]
            assert row["total_score"] is not None or row["quant_score"] is not None


def test_dashboard_highlights_at_least_ten_when_critic_rejects_all() -> None:
    tickers = list(NAMES)
    scores = [_score(t, 88 - i) for i, t in enumerate(tickers)]
    recs = [_rec(f"rec-{t}", t, verdict="rejected") for t in tickers[:3]]
    secs = [_security(t, n) for t, n in NAMES.items()]
    with _client(scores=scores, recs=recs, securities=secs) as client:
        body = client.get("/api/v1/dashboard", params={"market": "JP"}).json()
        recs_out = body["data"]["top_recommendations"]
        assert len(recs_out) == 10
        for row in recs_out:
            assert row["name_local"]
            assert row["name_local"] != row["ticker"]
            assert row["total_score"] is not None or row["quant_score"] is not None
        rejected = [row for row in recs_out if row.get("critic_verdict") == "rejected"]
        assert rejected
        assert all(row.get("critic_verdict") != "approved" for row in rejected)


def test_sector_filter_applies_to_universe() -> None:
    scores = [
        _score("7203", 80),
        _score("6758", 79),
        _score("4063", 70),
    ]
    secs = [
        _security("7203", "トヨタ自動車", "輸送用機器"),
        _security("6758", "ソニーグループ", "電気機器"),
        _security("4063", "信越化学工業", "化学"),
    ]
    with _client(scores=scores, recs=[], securities=secs) as client:
        body = client.get(
            "/api/v1/recommendations",
            params={"market": "JP", "sector": "輸送用機器"},
        ).json()
        tickers = [row["ticker"] for row in body["data"]["items"]]
        assert tickers == ["7203"]


def test_approved_filter_may_be_empty_when_user_narrows() -> None:
    scores = [_score("7203", 80), _score("6758", 70)]
    recs = [_rec("rec-7203", "7203", verdict="rejected")]
    secs = [_security("7203", "トヨタ自動車"), _security("6758", "ソニーグループ")]
    with _client(scores=scores, recs=recs, securities=secs) as client:
        body = client.get(
            "/api/v1/recommendations",
            params={"market": "JP", "critic_verdict": "approved"},
        ).json()
        assert body["data"]["items"] == []
        assert body["data"]["universe_size"] == 2
