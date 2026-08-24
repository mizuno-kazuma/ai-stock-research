"""ボラティリティ系の特徴量（docs/04-analysis-engine.md §1.3）。

`garch_vol_*` はここでは計算しない（`packages/core/models/garch.py`）。実現ボラは
GARCH 推定が収束しなかった銘柄のフォールバック先でもある。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from packages.core.factors.calendar import TRADING_DAYS_PER_YEAR
from packages.core.factors.panel import PricePanel, require_history

ANNUALIZER = float(np.sqrt(TRADING_DAYS_PER_YEAR))


def realized_vol(log_returns: pd.DataFrame, window: int) -> pd.Series:
    tail = log_returns.tail(window)
    counts = tail.notna().sum(axis=0)
    vol = tail.std(axis=0, ddof=1, skipna=True) * ANNUALIZER
    # 窓の8割以上データがある銘柄のみ有効とする。
    return vol.where(counts >= max(2, int(window * 0.8)))


def downside_deviation(log_returns: pd.DataFrame, window: int) -> pd.Series:
    tail = log_returns.tail(window)
    negative = tail.clip(upper=0.0)
    counts = tail.notna().sum(axis=0)
    dev = negative.std(axis=0, ddof=1, skipna=True) * ANNUALIZER
    return dev.where(counts >= max(2, int(window * 0.8)))


def max_drawdown(close: pd.DataFrame, window: int) -> pd.Series:
    tail = close.tail(window)
    if tail.empty:
        return pd.Series(dtype="float64")
    running_max = tail.cummax(axis=0)
    drawdown = tail / running_max.replace(0.0, np.nan) - 1.0
    counts = tail.notna().sum(axis=0)
    return drawdown.min(axis=0, skipna=True).where(counts >= max(2, int(window * 0.8)))


def market_beta(
    log_returns: pd.DataFrame, benchmark_returns: pd.Series, window: int = 252
) -> pd.Series:
    """`cov(ret, ret_bench) / var(ret_bench)`。

    ベンチマークが取得できない場合は NaN を返す（等ウェイト平均で代用しない。
    「市場」の定義がすり替わると beta の意味が変わるため）。
    """
    if log_returns.empty or benchmark_returns is None or benchmark_returns.empty:
        return pd.Series(np.nan, index=log_returns.columns, dtype="float64")
    bench = pd.to_numeric(benchmark_returns, errors="coerce")
    bench.index = pd.to_datetime(bench.index)
    aligned_bench = bench.reindex(log_returns.index)
    tail_stock = log_returns.tail(window)
    tail_bench = aligned_bench.tail(window)
    var_bench = tail_bench.var(ddof=1)
    if not np.isfinite(var_bench) or var_bench == 0:
        return pd.Series(np.nan, index=log_returns.columns, dtype="float64")
    demeaned_bench = tail_bench - tail_bench.mean()
    result: dict[str, float] = {}
    for ticker in tail_stock.columns:
        series = tail_stock[ticker]
        mask = series.notna() & tail_bench.notna()
        n = int(mask.sum())
        if n < max(30, int(window * 0.5)):
            result[ticker] = np.nan
            continue
        cov = float(
            (
                (series[mask] - series[mask].mean()) * demeaned_bench[mask]
            ).sum()
            / (n - 1)
        )
        var = float((demeaned_bench[mask] ** 2).sum() / (n - 1))
        result[ticker] = cov / var if var > 0 else np.nan
    return pd.Series(result, dtype="float64")


def average_true_range(panel: PricePanel, window: int = 14) -> pd.Series:
    """Wilder の ATR。"""
    if panel.is_empty:
        return pd.Series(dtype="float64")
    high = panel.get("adj_high")
    low = panel.get("adj_low")
    close = panel.close
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).stack(future_stack=True),
            (high - prev_close).abs().stack(future_stack=True),
            (low - prev_close).abs().stack(future_stack=True),
        ],
        axis=1,
    ).max(axis=1)
    true_range = tr.unstack()
    # Wilder の平滑化は alpha = 1/window の EMA と等価。
    atr = true_range.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    if atr.empty:
        return pd.Series(dtype="float64")
    return atr.iloc[-1]


def compute_volatility(
    panel: PricePanel, *, benchmark_returns: pd.Series | None = None
) -> pd.DataFrame:
    if panel.is_empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    log_ret = panel.log_returns
    lengths = panel.history_length()
    out = pd.DataFrame(index=pd.Index(panel.close.columns, name="ticker"))
    out["realized_vol_20d"] = require_history(realized_vol(log_ret, 20), lengths, 21)
    out["realized_vol_60d"] = require_history(realized_vol(log_ret, 60), lengths, 61)
    out["downside_dev_60d"] = require_history(
        downside_deviation(log_ret, 60), lengths, 61
    )
    out["max_drawdown_252d"] = require_history(
        max_drawdown(panel.close, 252), lengths, 200
    )
    out["beta_market_252d"] = require_history(
        market_beta(log_ret, benchmark_returns, 252)
        if benchmark_returns is not None
        else pd.Series(np.nan, index=out.index, dtype="float64"),
        lengths,
        200,
    )
    out["atr_14"] = require_history(average_true_range(panel, 14), lengths, 15)
    return out
