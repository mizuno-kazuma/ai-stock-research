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


def test_get_security_matches_jquants_padded_ticker() -> None:
    with DuckDBRepo.in_memory() as duck:
        duck.upsert_securities(
            [
                {
                    "ticker": "72030",
                    "market": "JP",
                    "name_local": "トヨタ自動車",
                    "currency": "JPY",
                    "valid_from": dt.date(2020, 1, 1),
                    "is_active": True,
                }
            ]
        )
        four = duck.get_security("7203", "JP")
        five = duck.get_security("72030", "JP")
        assert four is not None and five is not None
        assert four["name_local"] == five["name_local"] == "トヨタ自動車"


def test_search_securities_returns_one_row_per_issuer() -> None:
    """履歴行と JP の 4桁/5桁は検索では同一銘柄として畳む。"""
    with DuckDBRepo.in_memory() as duck:
        duck.upsert_securities(
            [
                {
                    "ticker": "7203",
                    "market": "JP",
                    "name_local": "トヨタ自動車",
                    "name_en": "Toyota Motor Corporation",
                    "sector_name": "輸送用機器",
                    "currency": "JPY",
                    "valid_from": dt.date(2020, 1, 1),
                    "is_active": True,
                },
                {
                    "ticker": "72030",
                    "market": "JP",
                    "name_local": "72030",
                    "currency": "JPY",
                    "valid_from": dt.date(2026, 8, 1),
                    "is_active": True,
                },
                {
                    "ticker": "72030",
                    "market": "JP",
                    "name_local": "トヨタ自動車",
                    "name_en": "TOYOTA MOTOR CORPORATION",
                    "sector_name": "輸送用機器",
                    "currency": "JPY",
                    "valid_from": dt.date(2026, 8, 18),
                    "is_active": True,
                },
                {
                    "ticker": "72030",
                    "market": "JP",
                    "name_local": "トヨタ自動車",
                    "name_en": "TOYOTA MOTOR CORPORATION",
                    "sector_name": "輸送用機器",
                    "currency": "JPY",
                    "valid_from": dt.date(2026, 8, 25),
                    "is_active": True,
                },
            ]
        )
        hits = duck.search_securities("7203", limit=10)
        assert [row["ticker"] for row in hits] == ["7203"]
        named = duck.search_securities("トヨタ", limit=10)
        assert len(named) == 1
        assert named[0]["ticker"] == "7203"
        assert named[0]["name_local"] == "トヨタ自動車"


def test_search_securities_collapses_same_five_digit_history() -> None:
    """画面で見えた 13010 / 15600 の二重表示。同じ 5 桁の現行行が複数あっても 1 件。"""
    with DuckDBRepo.in_memory() as duck:
        duck.upsert_securities(
            [
                {
                    "ticker": "14500",
                    "market": "JP",
                    "name_local": "TANAKEN",
                    "sector_name": "建設業",
                    "currency": "JPY",
                    "valid_from": dt.date(2026, 8, 1),
                    "is_active": True,
                },
                {
                    "ticker": "15600",
                    "market": "JP",
                    "name_local": "野村アセットマネジメント株式会社 NEXT FUNDS FTSEブルサ・マレーシアKLCI連動型上場投信",
                    "sector_name": "その他",
                    "currency": "JPY",
                    "valid_from": dt.date(2026, 8, 18),
                    "is_active": True,
                },
                {
                    "ticker": "15600",
                    "market": "JP",
                    "name_local": "野村アセットマネジメント株式会社 NEXT FUNDS FTSEブルサ・マレーシアKLCI連動型上場投信",
                    "sector_name": "その他",
                    "currency": "JPY",
                    "valid_from": dt.date(2026, 8, 25),
                    "is_active": True,
                },
                {
                    "ticker": "13010",
                    "market": "JP",
                    "name_local": "極洋",
                    "sector_name": "水産・農林業",
                    "currency": "JPY",
                    "valid_from": dt.date(2026, 8, 18),
                    "is_active": True,
                },
                {
                    "ticker": "13010",
                    "market": "JP",
                    "name_local": "極洋",
                    "sector_name": "水産・農林業",
                    "currency": "JPY",
                    "valid_from": dt.date(2026, 8, 25),
                    "is_active": True,
                },
            ]
        )
        by_code = duck.search_securities("15600", limit=10)
        assert [row["ticker"] for row in by_code] == ["15600"]
        kyokuyo = duck.search_securities("極", limit=10)
        assert [row["ticker"] for row in kyokuyo] == ["13010"]
        assert kyokuyo[0]["name_local"] == "極洋"


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


def test_get_documents_matches_jquants_padded_ticker() -> None:
    """EDINET は 4 桁、画面は 5 桁でも同一銘柄として返す。"""
    with DuckDBRepo.in_memory() as duck:
        n = duck.upsert_documents(
            [
                {
                    "doc_id": "edinet:S100TEST",
                    "ticker": "7203",
                    "market": "JP",
                    "source": "edinet",
                    "doc_type": "quarterly_report",
                    "title": "四半期報告書",
                    "filed_at": dt.datetime(2026, 8, 27, 15, 0, 0),
                    "source_url": "https://example.invalid/S100TEST",
                }
            ]
        )
        assert n == 1
        four = duck.get_documents(ticker="7203", market="JP")
        five = duck.get_documents(ticker="72030", market="JP")
        assert len(four) == 1
        assert len(five) == 1
        assert four[0]["doc_id"] == five[0]["doc_id"] == "edinet:S100TEST"
        assert duck.get_documents(ticker="130A", market="JP") == []


def test_upsert_documents_persists_name_local() -> None:
    with DuckDBRepo.in_memory() as duck:
        duck.upsert_documents(
            [
                {
                    "doc_id": "edinet:S100NAME",
                    "ticker": "7203",
                    "market": "JP",
                    "name_local": "トヨタ自動車株式会社",
                    "source": "edinet",
                    "doc_type": "quarterly_report",
                    "title": "四半期報告書",
                    "filed_at": dt.datetime(2026, 8, 27, 15, 0, 0),
                    "source_url": "https://example.invalid/S100NAME",
                }
            ]
        )
        row = duck.get_document("edinet:S100NAME")
        assert row is not None
        assert row["name_local"] == "トヨタ自動車株式会社"
