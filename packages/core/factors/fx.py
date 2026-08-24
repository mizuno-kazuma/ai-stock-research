"""為替感応度（docs/04-analysis-engine.md §1.9）。

直近60営業日での USD/JPY 変化率に対する銘柄リターンの回帰係数。輸出企業（円安で
恩恵）と輸入・内需企業（円高で恩恵）を区別するために使う。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from packages.core.factors.panel import PricePanel

MIN_OBSERVATIONS = 40


def fx_sensitivity(
    stock_returns: pd.DataFrame, fx_returns: pd.Series, *, window: int = 60
) -> pd.Series:
    """単回帰の傾き。切片ありの OLS を閉形式で解く。"""
    if stock_returns.empty or fx_returns is None or fx_returns.empty:
        return pd.Series(
            np.nan, index=getattr(stock_returns, "columns", []), dtype="float64"
        )
    fx = pd.to_numeric(fx_returns, errors="coerce")
    fx.index = pd.to_datetime(fx.index)
    fx = fx.reindex(stock_returns.index).tail(window)
    stock = stock_returns.tail(window)
    result: dict[str, float] = {}
    for ticker in stock.columns:
        series = stock[ticker]
        mask = series.notna() & fx.notna()
        n = int(mask.sum())
        if n < MIN_OBSERVATIONS:
            result[ticker] = np.nan
            continue
        x = fx[mask].to_numpy(dtype=float)
        y = series[mask].to_numpy(dtype=float)
        var_x = float(((x - x.mean()) ** 2).sum())
        if var_x <= 0:
            result[ticker] = np.nan
            continue
        result[ticker] = float(((x - x.mean()) * (y - y.mean())).sum() / var_x)
    return pd.Series(result, dtype="float64")


def compute_fx_features(
    panel: PricePanel, fx_series: pd.Series | None, *, window: int = 60
) -> pd.DataFrame:
    """`fx_sensitivity_60d`。USD/JPY が取れない場合は列だけ作って NULL。"""
    if panel.is_empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    out = pd.DataFrame(index=pd.Index(panel.close.columns, name="ticker"))
    if fx_series is None or len(fx_series) < MIN_OBSERVATIONS + 1:
        out[f"fx_sensitivity_{window}d"] = np.nan
        return out
    fx = pd.to_numeric(fx_series, errors="coerce")
    fx.index = pd.to_datetime(fx.index)
    fx_ret = fx.sort_index().pct_change(fill_method=None)
    out[f"fx_sensitivity_{window}d"] = fx_sensitivity(
        panel.simple_returns, fx_ret, window=window
    ).reindex(out.index)
    return out
