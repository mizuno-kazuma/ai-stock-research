"""目的変数（ラベル）の生成（docs/04-analysis-engine.md §3.2）。

`as_of` の翌営業日の始値で買い、`horizon` 営業日後の始値で売る前提のリターン。

終値ベースにしないのは、終値時点で計算した特徴量に基づいて終値で約定するのが
不可能だからである（これは頻出するリーク）。この1ステップのズレを入れない
バックテストは必ず良い結果を出し、実運用で再現しない。
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from packages.core.factors.calendar import TradingCalendar
from packages.core.factors.transforms import sector_demean


def make_label(
    prices: pd.DataFrame,
    as_of: date,
    horizon: int,
    *,
    ticker_col: str = "ticker",
    date_col: str = "trade_date",
    open_col: str = "adj_open",
    calendar: TradingCalendar | None = None,
) -> pd.Series:
    """`as_of` 基準の将来リターン。

    Returns:
        index=ticker の Series。エントリー日または決済日の価格が無い銘柄は NaN。
    """
    if prices.empty:
        return pd.Series(dtype="float64", name=f"fwd_ret_{horizon}d")
    cal = calendar or TradingCalendar.from_prices(prices, date_col=date_col)
    entry_date = cal.next_business_day(as_of)
    exit_date = cal.shift(entry_date, horizon)

    work = prices.copy()
    work[date_col] = pd.to_datetime(work[date_col], errors="coerce").dt.date
    work[ticker_col] = work[ticker_col].astype(str)
    prices_at = (
        work.loc[work[date_col].isin([entry_date, exit_date])]
        .drop_duplicates(subset=[ticker_col, date_col], keep="last")
        .pivot(index=ticker_col, columns=date_col, values=open_col)
    )
    if entry_date not in prices_at.columns or exit_date not in prices_at.columns:
        return pd.Series(dtype="float64", name=f"fwd_ret_{horizon}d")
    entry = pd.to_numeric(prices_at[entry_date], errors="coerce").where(lambda s: s > 0)
    exit_ = pd.to_numeric(prices_at[exit_date], errors="coerce")
    label = exit_ / entry - 1.0
    label.name = f"fwd_ret_{horizon}d"
    label.index.name = "ticker"
    return label


def make_excess_label(
    prices: pd.DataFrame,
    as_of: date,
    horizon: int,
    *,
    sectors: pd.Series | None = None,
    benchmark_return: float | None = None,
    calendar: TradingCalendar | None = None,
    **kwargs: object,
) -> pd.DataFrame:
    """超過リターン。既定はセクター中立（`stock_ret - sector_median_ret`）。

    ベンチマーク超過も別途計算して両方返す。
    """
    raw = make_label(prices, as_of, horizon, calendar=calendar, **kwargs)  # type: ignore[arg-type]
    out = pd.DataFrame({f"fwd_ret_{horizon}d": raw})
    if raw.empty:
        out[f"excess_ret_{horizon}d"] = pd.Series(dtype="float64")
        out[f"bench_excess_ret_{horizon}d"] = pd.Series(dtype="float64")
        return out
    if sectors is not None and not sectors.empty:
        frame = pd.DataFrame(
            {f"fwd_ret_{horizon}d": raw, "sector_code": sectors.reindex(raw.index)}
        )
        out[f"excess_ret_{horizon}d"] = sector_demean(frame, f"fwd_ret_{horizon}d")
    else:
        out[f"excess_ret_{horizon}d"] = raw - raw.median()
    out[f"bench_excess_ret_{horizon}d"] = (
        raw - benchmark_return if benchmark_return is not None else np.nan
    )
    return out


def build_label_panel(
    prices: pd.DataFrame,
    as_of_dates: list[date],
    horizon: int,
    *,
    sectors: pd.Series | None = None,
    calendar: TradingCalendar | None = None,
) -> pd.DataFrame:
    """複数 `as_of` 分のラベルを縦に積む。学習データ作成用。"""
    cal = calendar or TradingCalendar.from_prices(prices)
    frames: list[pd.DataFrame] = []
    for as_of in as_of_dates:
        chunk = make_excess_label(
            prices, as_of, horizon, sectors=sectors, calendar=cal
        )
        if chunk.empty:
            continue
        chunk = chunk.reset_index()
        chunk.insert(0, "as_of", as_of)
        frames.append(chunk)
    if not frames:
        return pd.DataFrame(
            columns=[
                "as_of",
                "ticker",
                f"fwd_ret_{horizon}d",
                f"excess_ret_{horizon}d",
                f"bench_excess_ret_{horizon}d",
            ]
        )
    return pd.concat(frames, ignore_index=True)
