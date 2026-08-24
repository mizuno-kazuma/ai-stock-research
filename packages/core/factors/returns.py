"""リターン・モメンタム系の特徴量（docs/04-analysis-engine.md §1.2）。

`as_of` の終値までの情報のみを使う。エントリーは翌営業日始値を想定するため
（`labels.py`）、当日終値の参照は先読みにならない。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from packages.core.factors.panel import PricePanel, lag_value, require_history
from packages.core.factors.transforms import sector_demean

RETURN_HORIZONS = (1, 5, 20, 60, 252)


def compute_returns(panel: PricePanel) -> pd.DataFrame:
    """`ret_Nd = adj_close[t] / adj_close[t-N] - 1`。"""
    if panel.is_empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    close = panel.close
    lengths = panel.history_length()
    latest = close.iloc[-1]
    out = pd.DataFrame(index=pd.Index(close.columns, name="ticker"))
    for n in RETURN_HORIZONS:
        base = lag_value(close, n)
        ratio = latest / base.replace(0.0, np.nan) - 1.0
        out[f"ret_{n}d"] = require_history(ratio, lengths, n + 1)
    return out


def compute_momentum(panel: PricePanel) -> pd.DataFrame:
    """モメンタム。`mom_12_1` は直近1ヶ月を除外する。

    直近1ヶ月を除外するのは短期反転効果を排除する標準実装。除外しないと
    「先月急騰した銘柄」を買い続けることになり、実運用で成績が落ちる。
    """
    if panel.is_empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    close = panel.close
    lengths = panel.history_length()
    latest = close.iloc[-1]
    out = pd.DataFrame(index=pd.Index(close.columns, name="ticker"))

    px_21 = lag_value(close, 21)
    out["mom_12_1"] = require_history(
        px_21 / lag_value(close, 252).replace(0.0, np.nan) - 1.0, lengths, 253
    )
    out["mom_6_1"] = require_history(
        px_21 / lag_value(close, 126).replace(0.0, np.nan) - 1.0, lengths, 127
    )

    window = close.tail(252)
    high_52w = window.max(axis=0, skipna=True)
    out["price_to_52w_high"] = require_history(
        latest / high_52w.replace(0.0, np.nan), lengths, 200
    )

    ma200 = close.tail(200).mean(axis=0, skipna=True)
    out["dist_from_ma200"] = require_history(
        latest / ma200.replace(0.0, np.nan) - 1.0, lengths, 200
    )
    return out


def compute_sector_relative(
    features: pd.DataFrame,
    sectors: pd.Series,
    *,
    col: str = "ret_20d",
    out_col: str = "sector_relative_ret_20d",
) -> pd.Series:
    """`ret_20d - median(ret_20d)`（同セクター内）。"""
    if features.empty or col not in features.columns:
        return pd.Series(dtype="float64", name=out_col)
    work = features[[col]].copy()
    work["sector_code"] = sectors.reindex(work.index)
    result = sector_demean(work, col)
    result.name = out_col
    return result
