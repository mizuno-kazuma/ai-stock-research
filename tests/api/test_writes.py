"""ストレージ往復と書き込み系エンドポイント。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_trade_roundtrip(client: TestClient) -> None:
    created = client.post(
        "/api/v1/trades",
        json={
            "ticker": "7203",
            "market": "JP",
            "side": "buy",
            "quantity": 100,
            "price": 3125.0,
            "fee": 275.0,
            "currency": "JPY",
            "executed_at": "2026-08-22T00:15:00Z",
            "broker": "楽天証券",
            "account_type": "特定",
            "thesis_ja": "テスト投入",
            "emotion_tag": "neutral",
        },
    )
    assert created.status_code == 200, created.text
    trade_id = created.json()["data"]["trade_id"]
    listed = client.get("/api/v1/trades")
    ids = {t["trade_id"] for t in listed.json()["data"]["items"]}
    assert trade_id in ids
    patched = client.patch(f"/api/v1/trades/{trade_id}", json={"review_ja": "振り返り"})
    assert patched.status_code == 200
    assert patched.json()["data"]["review_ja"] == "振り返り"
    deleted = client.delete(f"/api/v1/trades/{trade_id}")
    assert deleted.status_code == 200


def test_settings_roundtrip(client: TestClient) -> None:
    r = client.patch("/api/v1/settings", json={"ui.direction_colors": "us", "llm.daily_cap_usd": 1.5})
    assert r.status_code == 200, r.text
    values = r.json()["data"]["values"]
    assert values["ui.direction_colors"] == "us"
    assert values["llm.daily_cap_usd"] == 1.5
    got = client.get("/api/v1/settings")
    assert got.json()["data"]["values"]["ui.direction_colors"] == "us"


def test_watchlist_roundtrip(client: TestClient) -> None:
    r = client.post("/api/v1/watchlist", json={"ticker": "9984", "market": "JP"})
    assert r.status_code == 200, r.text
    tickers = {i["ticker"] for i in r.json()["data"]["items"]}
    assert "9984" in tickers
    d = client.delete("/api/v1/watchlist/JP/9984")
    assert d.status_code == 200


def test_stock_from_seeded_warehouse(client: TestClient) -> None:
    r = client.get("/api/v1/stocks/JP/7203")
    assert r.status_code == 200
    assert r.json()["data"]["security"]["ticker"] == "7203"
    prices = client.get("/api/v1/stocks/JP/7203/prices?series=research")
    assert prices.status_code == 200
    assert prices.json()["data"]["source"]
    assert prices.json()["data"]["series"] == "research"


def test_recommendation_card_invariants(client: TestClient) -> None:
    r = client.get("/api/v1/recommendations/01J8XKQ3M4N5P6R7S8T9V0W1X2")
    assert r.status_code == 200, r.text
    card = r.json()["data"]
    assert len(card["bear_case_ja"]) >= 20
    assert card["citations"]
    assert card["expected_ret_lo"] is not None
    assert card["expected_ret_hi"] is not None
