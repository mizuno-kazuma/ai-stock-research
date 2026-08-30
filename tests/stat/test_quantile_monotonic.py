"""T-STAT-05: スコア5分位のリターンが概ね単調であること。"""

from __future__ import annotations

import pandas as pd

from packages.core.backtest.engine import _quantile_returns


def test_quantile_returns_are_monotonic_in_backtest() -> None:
    trades = pd.DataFrame(
        {
            "score": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0] * 3,
            "raw_return": [-0.04, -0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05] * 3,
        }
    )
    q_returns = _quantile_returns(trades)
    assert len(q_returns) == 5
    assert q_returns[4] > q_returns[0]
