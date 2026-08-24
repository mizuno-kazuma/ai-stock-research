"""価格データの品質チェック。

docs/02-data-ingestion.md §3.3。yfinance は静かに壊れるため必須である。
「除外する」ものと「フラグを立てるが除外しない」ものを明確に分ける。
実際に起きうる変動（±40%超）を除外すると、真のイベントを消してしまう。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

EXTREME_MOVE_THRESHOLD = 0.40
# 日本株の価格が3桁小さい等の通貨混在を検出する下限（円建てで 10 円未満は異常）。
JPY_MIN_PLAUSIBLE_PRICE = 10.0


@dataclass(slots=True)
class QualityResult:
    rejected: bool = False
    flags: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def add_flag(self, code: str, reason: str = "") -> None:
        if code not in self.flags:
            self.flags.append(code)
        if reason:
            self.reasons.append(reason)

    def reject(self, code: str, reason: str) -> None:
        self.rejected = True
        self.add_flag(code, reason)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def validate_price_row(
    row: dict[str, Any],
    *,
    prev_close: float | None = None,
    has_corporate_action: bool = False,
    currency: str | None = None,
) -> QualityResult:
    """1行分の OHLCV を検査する（T-DQ-01）。"""
    result = QualityResult()

    close = row.get("close")
    if _is_missing(close):
        result.reject("CLOSE_MISSING", "close が欠損")
        return result

    high, low, open_ = row.get("high"), row.get("low"), row.get("open")
    close = float(close)

    if not _is_missing(high) and not _is_missing(low):
        high_f, low_f = float(high), float(low)
        if high_f < low_f:
            result.reject("HIGH_LOW_INVERTED", f"high({high_f}) < low({low_f})")
            return result
        if not (low_f <= close <= high_f):
            result.reject("CLOSE_OUT_OF_RANGE", f"close({close}) が [low, high] の外")
            return result
        if not _is_missing(open_) and not (low_f <= float(open_) <= high_f):
            result.reject("OPEN_OUT_OF_RANGE", f"open({open_}) が [low, high] の外")
            return result

    if close <= 0:
        result.reject("NON_POSITIVE_PRICE", f"close({close}) が非正")
        return result

    if currency == "JPY" and close < JPY_MIN_PLAUSIBLE_PRICE:
        result.reject("CURRENCY_MISMATCH", f"JPY 建てで close={close} は桁が疑わしい")
        return result

    # --- 以下は除外せずフラグのみ ---
    if prev_close and prev_close > 0:
        change = abs(close / prev_close - 1.0)
        if change > EXTREME_MOVE_THRESHOLD and not has_corporate_action:
            result.add_flag("EXTREME_MOVE", f"前日比 {change:.1%}")

    volume = row.get("volume")
    if not _is_missing(volume) and float(volume) == 0:
        if prev_close and not math.isclose(close, float(prev_close), rel_tol=1e-9):
            result.add_flag("ZERO_VOLUME_PRICE_MOVED", "出来高0で価格が動いている")

    return result


def validate_price_frame(
    df: pd.DataFrame,
    *,
    currency_col: str = "currency",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """DataFrame 全体を検査し `(採用行, 除外行)` を返す。

    - 同一 `(ticker, trade_date)` の重複は最後の1件を採用する
    - 除外行には `reject_reason` を付ける
    - 採用行には `quality_flags` を付ける
    """
    if df.empty:
        empty = df.copy()
        empty["quality_flags"] = pd.Series(dtype=object)
        return empty, df.copy()

    work = df.copy()
    if {"ticker", "trade_date"}.issubset(work.columns):
        work = work.drop_duplicates(subset=["ticker", "trade_date"], keep="last")
    if {"ticker", "trade_date"}.issubset(work.columns):
        work = work.sort_values(["ticker", "trade_date"]).reset_index(drop=True)

    prev_close_map: dict[str, float] = {}
    flags: list[list[str]] = []
    rejected_mask: list[bool] = []
    reasons: list[str] = []

    for record in work.to_dict("records"):
        ticker = str(record.get("ticker", ""))
        result = validate_price_row(
            record,
            prev_close=prev_close_map.get(ticker),
            has_corporate_action=bool(record.get("has_corporate_action", False)),
            currency=record.get(currency_col),
        )
        flags.append(result.flags)
        rejected_mask.append(result.rejected)
        reasons.append("; ".join(result.reasons))
        if not result.rejected and not _is_missing(record.get("close")):
            prev_close_map[ticker] = float(record["close"])

    work["quality_flags"] = flags
    work["reject_reason"] = reasons
    mask = pd.Series(rejected_mask, index=work.index)
    accepted = work.loc[~mask].drop(columns=["reject_reason"])
    rejected = work.loc[mask]
    return accepted.reset_index(drop=True), rejected.reset_index(drop=True)
