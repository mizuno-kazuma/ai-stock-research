"""DuckDB / SQLite の公開 API 往復。"""

from __future__ import annotations

import datetime as dt

from packages.core.storage import DuckDBRepo, SQLiteRepo


def test_duckdb_security_and_price_roundtrip() -> None:
    with DuckDBRepo.in_memory() as duck:
        n = duck.upsert_securities(
            [
                {
                    "ticker": "7203",
                    "market": "JP",
                    "name_local": "トヨタ自動車",
                    "currency": "JPY",
                    "valid_from": dt.date(2020, 1, 1),
                    "is_active": True,
                }
            ]
        )
        assert n == 1
        sec = duck.get_security("7203", "JP")
        assert sec is not None
        assert sec["name_local"] == "トヨタ自動車"
        duck.upsert_prices_daily(
            [
                {
                    "ticker": "7203",
                    "market": "JP",
                    "trade_date": dt.date(2026, 5, 30),
                    "close": 3074,
                    "adj_close": 3074,
                    "currency": "JPY",
                    "source": "jquants",
                }
            ]
        )
        close = duck.get_latest_close("7203", "JP", as_of=dt.date(2026, 6, 1))
        assert close is not None
        assert close["close"] == 3074


def test_sqlite_settings_and_trade_roundtrip() -> None:
    with SQLiteRepo.in_memory() as state:
        state.set_setting("ui.direction_colors", "jp")
        assert state.get_setting("ui.direction_colors") == "jp"
        trade = state.insert_trade(
            trade_id="tr_test",
            ticker="7203",
            market="JP",
            side="buy",
            quantity=100,
            price=3125,
            fee=0,
            currency="JPY",
            executed_at="2026-08-22T00:00:00Z",
        )
        assert trade.trade_id == "tr_test"
        found = state.get_trade("tr_test")
        assert found is not None
        assert state.delete_trade("tr_test") is True
