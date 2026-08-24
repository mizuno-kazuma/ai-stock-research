"""価格パネル（日付 × 銘柄のワイド行列）。

長形式の `prices_daily` を毎回 groupby するのは遅く、かつ「うっかり未来行を
含める」事故が起きやすい。ここで一度だけ `as_of` で切ったワイド行列を作り、
以降のローリング計算はすべてこのパネル上で行う。

すべての行列は `index = trade_date（昇順、as_of 以下）`、`columns = ticker`。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import cached_property

import numpy as np
import pandas as pd

PRICE_COLUMNS = (
    "adj_open",
    "adj_high",
    "adj_low",
    "adj_close",
    "volume",
    "turnover_value",
)


@dataclass(frozen=True)
class PricePanel:
    """`as_of` 時点までの価格パネル。"""

    as_of: date
    frames: dict[str, pd.DataFrame]
    tickers: list[str]

    @classmethod
    def from_long(
        cls,
        prices: pd.DataFrame,
        as_of: date,
        *,
        ticker_col: str = "ticker",
        date_col: str = "trade_date",
        columns: tuple[str, ...] = PRICE_COLUMNS,
    ) -> PricePanel:
        if prices.empty:
            return cls(as_of=as_of, frames={}, tickers=[])
        work = prices.copy()
        work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
        cutoff = pd.Timestamp(as_of)
        work = work.loc[work[date_col].notna() & (work[date_col] <= cutoff)]
        if work.empty:
            return cls(as_of=as_of, frames={}, tickers=[])
        work[ticker_col] = work[ticker_col].astype(str)
        # 同一 (ticker, date) の重複は後勝ち（訂正データが後から来る想定）。
        work = work.drop_duplicates(subset=[ticker_col, date_col], keep="last")
        frames: dict[str, pd.DataFrame] = {}
        for col in columns:
            if col not in work.columns:
                continue
            wide = work.pivot(index=date_col, columns=ticker_col, values=col)
            frames[col] = wide.sort_index().astype("float64")
        if not frames:
            return cls(as_of=as_of, frames={}, tickers=[])
        any_frame = next(iter(frames.values()))
        tickers = [str(t) for t in any_frame.columns]
        # 全列を同じ形に揃える。欠けている列は NaN 行列で埋める（ゼロ埋めはしない）。
        template = any_frame
        for col in columns:
            if col not in frames:
                frames[col] = pd.DataFrame(
                    np.nan, index=template.index, columns=template.columns
                )
            else:
                frames[col] = frames[col].reindex(
                    index=template.index, columns=template.columns
                )
        return cls(as_of=as_of, frames=frames, tickers=tickers)

    def __len__(self) -> int:
        return len(self.index)

    @property
    def index(self) -> pd.DatetimeIndex:
        if not self.frames:
            return pd.DatetimeIndex([])
        return next(iter(self.frames.values())).index  # type: ignore[return-value]

    @property
    def is_empty(self) -> bool:
        return not self.frames or len(self.index) == 0

    def get(self, name: str) -> pd.DataFrame:
        if name not in self.frames:
            raise KeyError(f"panel has no column {name!r}: {sorted(self.frames)}")
        return self.frames[name]

    @property
    def close(self) -> pd.DataFrame:
        return self.get("adj_close")

    @cached_property
    def log_returns(self) -> pd.DataFrame:
        close = self.close
        return np.log(close.where(close > 0)).diff()

    @cached_property
    def simple_returns(self) -> pd.DataFrame:
        close = self.close
        return close.where(close > 0).pct_change(fill_method=None)

    def history_length(self) -> pd.Series:
        """銘柄ごとの有効な終値本数。履歴不足判定に使う。"""
        return self.close.notna().sum(axis=0)

    def last_row(self, name: str) -> pd.Series:
        frame = self.get(name)
        if frame.empty:
            return pd.Series(dtype="float64")
        return frame.iloc[-1]


def lag_value(frame: pd.DataFrame, lag: int) -> pd.Series:
    """`lag` 本前の値。履歴が足りない銘柄は NaN。"""
    if frame.empty or len(frame) <= lag:
        return pd.Series(np.nan, index=frame.columns, dtype="float64")
    return frame.iloc[-1 - lag]


def require_history(values: pd.Series, lengths: pd.Series, minimum: int) -> pd.Series:
    """履歴長が足りない銘柄を NULL にする。

    欠損規則: ゼロ埋め・平均埋めは「平均的な銘柄」という誤った情報を注入するので
    行わない（docs/04-analysis-engine.md §1.10）。
    """
    mask = lengths.reindex(values.index) >= minimum
    return values.where(mask.fillna(False))
