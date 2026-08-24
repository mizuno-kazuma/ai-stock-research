"""バックテストの成績指標。無リスク利子率は呼び出し側が渡す。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from packages.core.factors.calendar import TRADING_DAYS_PER_YEAR


@dataclass(frozen=True, slots=True)
class Drawdown:
    max_drawdown: float
    start: date | None
    end: date | None
    trough: date | None


def annualize_return(total_return: float, n_days: int) -> float:
    if n_days <= 0:
        return float("nan")
    years = n_days / TRADING_DAYS_PER_YEAR
    if years <= 0:
        return float("nan")
    if total_return <= -1.0:
        return -1.0
    return float((1.0 + total_return) ** (1.0 / years) - 1.0)


def sharpe_ratio(returns: np.ndarray, *, rf_daily: float = 0.0) -> float:
    excess = np.asarray(returns, dtype=float) - rf_daily
    excess = excess[np.isfinite(excess)]
    if excess.size < 2:
        return float("nan")
    vol = float(np.std(excess, ddof=1))
    if vol == 0:
        return 0.0
    return float(np.mean(excess) / vol * np.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(returns: np.ndarray, *, rf_daily: float = 0.0) -> float:
    excess = np.asarray(returns, dtype=float) - rf_daily
    excess = excess[np.isfinite(excess)]
    downside = excess[excess < 0]
    if excess.size < 2 or downside.size == 0:
        return float("nan")
    den = float(np.std(downside, ddof=1))
    if den == 0:
        return 0.0
    return float(np.mean(excess) / den * np.sqrt(TRADING_DAYS_PER_YEAR))


def max_drawdown(equity: pd.Series) -> Drawdown:
    if equity.empty:
        return Drawdown(max_drawdown=0.0, start=None, end=None, trough=None)
    running_max = equity.cummax()
    dd = equity / running_max.replace(0.0, np.nan) - 1.0
    trough_idx = dd.idxmin()
    max_dd = float(dd.min()) if np.isfinite(dd.min()) else 0.0
    # ピークは trough 以前の最高値。
    peak_idx = equity.loc[:trough_idx].idxmax() if trough_idx is not None else None
    recovered = None
    if trough_idx is not None:
        after = equity.loc[trough_idx:]
        peak_val = float(equity.loc[peak_idx]) if peak_idx is not None else None
        if peak_val is not None:
            hit = after[after >= peak_val]
            if not hit.empty:
                recovered = hit.index[0]
    return Drawdown(
        max_drawdown=max_dd,
        start=_as_date(peak_idx),
        end=_as_date(recovered),
        trough=_as_date(trough_idx),
    )


def calmar_ratio(cagr: float, mdd: float) -> float:
    if mdd == 0 or not np.isfinite(mdd):
        return float("nan")
    return float(cagr / abs(mdd))


def information_ratio(excess: np.ndarray) -> float:
    x = np.asarray(excess, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 2:
        return float("nan")
    vol = float(np.std(x, ddof=1))
    if vol == 0:
        return 0.0
    return float(np.mean(x) / vol * np.sqrt(TRADING_DAYS_PER_YEAR))


def _as_date(value: object) -> date | None:
    if value is None or (isinstance(value, float) and not np.isfinite(value)):
        return None
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return None
    return ts.date()
