"""T-DQ-05: 負の PER は NULL。earnings_yield は負値として残す。"""

from __future__ import annotations

import pandas as pd
import pytest

from packages.core.factors.fundamentals import compute_valuation


def test_negative_per_becomes_null() -> None:
    ttm = pd.DataFrame(
        {
            "net_income_ttm": [-100.0],
            "forecast_net_income": [-80.0],
            "total_equity": [800.0],
            "revenue_ttm": [2000.0],
            "total_debt": [100.0],
            "cash_and_equiv": [50.0],
            "ebitda_ttm": [-20.0],
            "operating_cf_ttm": [10.0],
            "capex_ttm": [-5.0],
            "dividend_per_share_ttm": [0.0],
        },
        index=pd.Index(["7203"], name="ticker"),
    )
    caps = pd.Series({"7203": 1000.0})
    close = pd.Series({"7203": 10.0})
    frame = compute_valuation(ttm, market_cap=caps, close=close)
    assert pd.isna(frame.loc["7203", "per"])
    assert frame.loc["7203", "earnings_yield"] == pytest.approx(-0.1)
