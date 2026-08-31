"""ダッシュボード「今週の開示」の件数。シード週と翌週で差が出ることを固定する。"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from packages.core.config import get_settings
from services.api.deps import AppState
from services.api.events import EventBus
from services.api.routers.dashboard import _dashboard_from_seed, _dashboard_from_warehouse
from services.api.util import utc_now


def test_seed_dashboard_counts_sample_week(client: TestClient) -> None:
    r = client.get("/api/v1/dashboard?market=JP&as_of=2026-08-22")
    assert r.status_code == 200
    body = r.json()
    data = body["data"]
    assert body["meta"]["as_of"] == "2026-08-22"
    assert data["new_filings_count"] == 5
    assert {row["ticker"] for row in data["watchlist_filings"]} == {"6758", "7203", "9432", "AAPL", "NVDA"}


def test_seed_dashboard_omitted_as_of_uses_sample_meta(client: TestClient) -> None:
    r = client.get("/api/v1/dashboard?market=JP")
    assert r.status_code == 200
    body = r.json()
    assert body["meta"]["as_of"] == "2026-08-22"
    assert body["data"]["new_filings_count"] == 5


def test_seed_dashboard_following_week_is_empty(client: TestClient) -> None:
    r = client.get("/api/v1/dashboard?market=JP&as_of=2026-08-29")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["as_of"] == "2026-08-29"
    assert data["new_filings_count"] == 0
    assert data["watchlist_filings"] == []


def test_warehouse_counts_sample_week_only(seeded_repos) -> None:
    duck, sqlite, payload = seeded_repos
    state = AppState(
        settings=get_settings(),
        duck=duck,
        sqlite=sqlite,
        bus=EventBus(),
        started_at=utc_now(),
        payload={},
    )
    sample_week = _dashboard_from_warehouse(state, market="JP", as_of=date(2026, 8, 22))
    assert sample_week.new_filings_count == 3
    assert {row.ticker for row in sample_week.watchlist_filings} == {"6758", "7203", "9432"}

    this_week = _dashboard_from_warehouse(state, market="JP", as_of=date(2026, 8, 29))
    assert this_week.new_filings_count == 0
    assert this_week.watchlist_filings == []

    state.payload = payload
    seed_sample = _dashboard_from_seed(state, market="JP", as_of=date(2026, 8, 22))
    assert seed_sample.new_filings_count == 5
    seed_this_week = _dashboard_from_seed(state, market="JP", as_of=date(2026, 8, 29))
    assert seed_this_week.new_filings_count == 0


def test_warehouse_watchlist_matches_jquants_padded_ticker(seeded_repos) -> None:
    duck, sqlite, _payload = seeded_repos
    sqlite.add_to_watchlist("72030", "JP")
    state = AppState(
        settings=get_settings(),
        duck=duck,
        sqlite=sqlite,
        bus=EventBus(),
        started_at=utc_now(),
        payload={},
    )
    sample_week = _dashboard_from_warehouse(state, market="JP", as_of=date(2026, 8, 22))
    tickers = {row.ticker for row in sample_week.watchlist_filings}
    assert "7203" in tickers
