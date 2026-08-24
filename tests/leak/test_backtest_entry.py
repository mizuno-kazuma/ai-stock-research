"""T-LEAK-05 / T-LEAK-06: エントリーは翌営業日始値、コスト引数は必須。"""

from __future__ import annotations

import inspect
from datetime import date

import pandas as pd
import pytest

from packages.core.backtest.engine import run_backtest
from packages.core.factors.screening import UniverseFilter


def _fixture_prices() -> pd.DataFrame:
    days = [
        date(2026, 8, 17),
        date(2026, 8, 18),
        date(2026, 8, 19),
        date(2026, 8, 20),
        date(2026, 8, 21),
        date(2026, 8, 24),
        date(2026, 8, 25),
        date(2026, 8, 26),
        date(2026, 8, 27),
        date(2026, 8, 28),
        date(2026, 8, 31),
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
        date(2026, 9, 4),
    ]
    rows = []
    px = 100.0
    for d in days:
        rows.append(
            {
                "ticker": "7203",
                "market": "JP",
                "trade_date": d,
                "open": px,
                "adj_open": px,
                "close": px + 1,
                "adj_close": px + 1,
                "volume": 1_000_000,
                "turnover_value": 1e8,
            }
        )
        px += 1.0
    # 翌営業日始値が識別できるように 8/21 だけ 200 にする。
    for r in rows:
        if r["trade_date"] == date(2026, 8, 21):
            r["adj_open"] = 200.0
            r["open"] = 200.0
    return pd.DataFrame(rows)


def test_backtest_entry_is_next_day_open() -> None:
    signals = pd.DataFrame(
        {"as_of": [date(2026, 8, 20)], "ticker": ["7203"], "score": [1.0]}
    )
    result = run_backtest(
        signals=signals,
        prices=_fixture_prices(),
        market="JP",
        period=(date(2026, 8, 17), date(2026, 9, 4)),
        rebalance_freq="weekly",
        n_positions=1,
        fee_bps=5.0,
        slippage_bps=10.0,
        max_turnover_pct=30.0,
        n_trials=1,
        universe_filter=UniverseFilter(market="JP", require_features_complete=False),
        benchmark="TOPIX",
    )
    trade = result.trades.iloc[0]
    assert trade["entry_date"] == date(2026, 8, 21)
    assert trade["entry_price"] == 200.0


def test_backtest_requires_cost_parameters() -> None:
    sig = inspect.signature(run_backtest)
    for name in ["fee_bps", "slippage_bps", "max_turnover_pct", "n_trials"]:
        param = sig.parameters[name]
        assert param.default is inspect.Parameter.empty, f"{name} にデフォルト値があります"
        assert param.kind == inspect.Parameter.KEYWORD_ONLY, f"{name} はキーワード専用引数にしてください"


def test_backtest_rejects_positional_cost_args() -> None:
    with pytest.raises(TypeError):
        run_backtest(  # type: ignore[misc]
            pd.DataFrame(),
            pd.DataFrame(),
            "JP",
            (date(2024, 1, 1), date(2024, 6, 1)),
            "weekly",
            1,
            5.0,
            10.0,
            30.0,
            1,
        )
