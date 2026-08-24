"""テクニカル指標（docs/04-analysis-engine.md §1.4）。

テクニカル単独での予測力は極めて弱いという前提で扱う。合成スコアではモメンタムと
強く相関するため重複計上を避け（相関チェックは `models/ranker.py`）、主に
エントリータイミングの参考情報として UI に出す。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from packages.core.factors.panel import PricePanel, require_history


def rsi(close: pd.DataFrame, window: int = 14) -> pd.Series:
    """Wilder の RSI。"""
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    if avg_gain.empty:
        return pd.Series(dtype="float64")
    rs = avg_gain.iloc[-1] / avg_loss.iloc[-1].replace(0.0, np.nan)
    result = 100.0 - 100.0 / (1.0 + rs)
    # 下落がゼロの区間は RSI = 100（rs が無限大）。
    all_gain = (avg_loss.iloc[-1] == 0) & (avg_gain.iloc[-1] > 0)
    return result.mask(all_gain, 100.0)


def macd(close: pd.DataFrame) -> pd.DataFrame:
    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    line = ema12 - ema26
    signal = line.ewm(span=9, adjust=False, min_periods=9).mean()
    if line.empty:
        return pd.DataFrame(columns=["macd", "macd_signal", "macd_hist"])
    return pd.DataFrame(
        {
            "macd": line.iloc[-1],
            "macd_signal": signal.iloc[-1],
            "macd_hist": line.iloc[-1] - signal.iloc[-1],
        }
    )


def bollinger_pct_b(close: pd.DataFrame, window: int = 20, n_std: float = 2.0) -> pd.Series:
    tail = close.tail(window)
    if tail.empty:
        return pd.Series(dtype="float64")
    mean = tail.mean(axis=0, skipna=True)
    std = tail.std(axis=0, ddof=1, skipna=True)
    upper = mean + n_std * std
    lower = mean - n_std * std
    width = (upper - lower).replace(0.0, np.nan)
    return (close.iloc[-1] - lower) / width


def compute_technicals(panel: PricePanel) -> pd.DataFrame:
    if panel.is_empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    close = panel.close
    lengths = panel.history_length()
    out = pd.DataFrame(index=pd.Index(close.columns, name="ticker"))
    out["rsi_14"] = require_history(rsi(close, 14), lengths, 15)
    macd_frame = macd(close).reindex(out.index)
    for col in ("macd", "macd_signal", "macd_hist"):
        out[col] = require_history(macd_frame[col], lengths, 35)
    out["bb_pct_b_20"] = require_history(bollinger_pct_b(close, 20), lengths, 20)
    return out
