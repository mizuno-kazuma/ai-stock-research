"""価格品質チェックの棄却を data_gaps / data_quality_flags に残す（F05）。"""

from __future__ import annotations

from datetime import date

from packages.core.connectors.base import RawBatch
from packages.core.connectors.jquants import JQuantsConnector
from packages.core.storage import DuckDBRepo


def _connector(tmp_path, warehouse) -> JQuantsConnector:
    return JQuantsConnector(
        data_dir=tmp_path,
        warehouse=warehouse,
        plan="light",
        env={"JQUANTS_PLAN": "light", "JQUANTS_API_KEY": "test-key"},
        require_enabled=True,
    )


def _price_row(
    *,
    code: str = "7203",
    day: str,
    open_: float | None = 3000.0,
    high: float | None = 3050.0,
    low: float | None = 2980.0,
    close: float | None = 3020.0,
    volume: float | None = 1_000_000,
) -> dict:
    return {
        "Code": code,
        "Date": day,
        "O": open_,
        "H": high,
        "L": low,
        "C": close,
        "Vo": volume,
    }


def test_nan_close_and_inverted_high_low_are_recorded(tmp_path) -> None:
    duck = DuckDBRepo.in_memory()
    connector = _connector(tmp_path, duck)
    batch = RawBatch(
        source="jquants",
        endpoint="equities_bars_daily",
        as_of=date(2026, 8, 28),
        payload={
            "data": [
                _price_row(day="2026-08-26", close=3000.0, high=3010.0, low=2990.0),
                _price_row(day="2026-08-27", close=None, high=3010.0, low=2990.0),
                _price_row(day="2026-08-28", close=3000.0, high=2900.0, low=3100.0),
            ]
        },
    )
    frame = connector.normalize(batch)
    n = connector.upsert(frame)
    connector.close()

    prices = duck.query("SELECT trade_date, close FROM prices_daily ORDER BY trade_date")
    assert [str(r["trade_date"])[:10] for r in prices] == ["2026-08-26"]
    assert n == 1

    gaps = duck.query("SELECT source, entity, reason, gap_start FROM data_gaps ORDER BY gap_start")
    assert len(gaps) == 2
    assert {str(g["reason"]) for g in gaps} == {"quality_reject"}
    assert {g["source"] for g in gaps} == {"jquants"}
    assert {g["entity"] for g in gaps} == {"7203"}

    flags = duck.query(
        "SELECT flag_code, table_name, entity FROM data_quality_flags ORDER BY flag_code"
    )
    codes = {row["flag_code"] for row in flags}
    assert "CLOSE_MISSING" in codes
    assert "HIGH_LOW_INVERTED" in codes
    assert {row["table_name"] for row in flags} == {"prices_daily"}
    duck.close()


def test_good_rows_upsert_and_extreme_move_is_flagged_not_dropped(tmp_path) -> None:
    duck = DuckDBRepo.in_memory()
    connector = _connector(tmp_path, duck)
    batch = RawBatch(
        source="jquants",
        endpoint="equities_bars_daily",
        as_of=date(2026, 8, 28),
        payload={
            "data": [
                _price_row(day="2026-08-26", close=1000.0, high=1010.0, low=990.0, open_=1000.0),
                _price_row(day="2026-08-27", close=1600.0, high=1610.0, low=1590.0, open_=1600.0),
            ]
        },
    )
    frame = connector.normalize(batch)
    n = connector.upsert(frame)
    connector.close()
    assert n == 2
    prices = duck.query("SELECT trade_date FROM prices_daily ORDER BY trade_date")
    assert len(prices) == 2
    gaps = duck.query("SELECT * FROM data_gaps")
    assert gaps == []
    flags = duck.query("SELECT flag_code FROM data_quality_flags")
    assert {row["flag_code"] for row in flags} == {"EXTREME_MOVE"}
    duck.close()
