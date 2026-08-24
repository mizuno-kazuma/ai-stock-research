"""PIT（Point-In-Time）ガード。

特徴量計算で最も起こりやすい事故は「未来の情報が混入している」ことで、しかも
それは精度が上がる方向に働くので気づきにくい。ここでは未来参照を
*構造的に不可能* にする道具を置く。

設計方針:
- 特徴量関数は生の DataFrame を受け取らず `PitFrame` を受け取る。
  `PitFrame` は `as_of` より後の行を物理的に落としてから返す。
- 財務・開示は「公開日」ベースに変換してからでないと参照できない。
- リーク検証は `assert_stable_under_future_data` で自動化する
  （.cursor/skills/add-analysis-factor の必須チェック）。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import pandas as pd

from packages.core.factors.calendar import TradingCalendar, effective_dates


class LeakError(AssertionError):
    """未来情報の参照、または未来データ追加で出力が変わったことを示す。"""


@dataclass(frozen=True)
class PitFrame:
    """`as_of` 時点で参照可能な行だけを見せる DataFrame ラッパ。

    Attributes:
        frame: 元データ。
        as_of: 情報カットオフ日。`as_of` 当日の *終値までに公開された* 情報は含む
            （docs/03-data-model.md §2.7）。エントリーは翌営業日始値を想定するため、
            当日終値の参照は先読みにならない。
        time_col: 時間軸となる列名。
    """

    frame: pd.DataFrame
    as_of: date
    time_col: str

    def __post_init__(self) -> None:
        if self.time_col not in self.frame.columns:
            raise KeyError(f"time column {self.time_col!r} not in frame: {list(self.frame.columns)}")

    @property
    def visible(self) -> pd.DataFrame:
        """`as_of` 以前の行のみ。以降の呼び出し側はこれしか触れない。"""
        times = _as_date_series(self.frame[self.time_col])
        mask = times.notna() & (times <= self.as_of)
        out = self.frame.loc[mask].copy()
        out[self.time_col] = times.loc[mask]
        return out

    def sorted_visible(self, by: Iterable[str]) -> pd.DataFrame:
        return self.visible.sort_values(list(by), kind="mergesort").reset_index(drop=True)

    def with_as_of(self, as_of: date) -> PitFrame:
        return PitFrame(frame=self.frame, as_of=as_of, time_col=self.time_col)


@dataclass
class PitContext:
    """1 回の特徴量計算に渡す入力一式。

    各入力は `PitFrame` として保持され、`as_of` を一括で切り替えられる。
    """

    as_of: date
    market: str = "JP"
    calendar: TradingCalendar = field(default_factory=TradingCalendar)
    inputs: dict[str, PitFrame] = field(default_factory=dict)

    def add(self, name: str, frame: pd.DataFrame, time_col: str) -> PitContext:
        self.inputs[name] = PitFrame(frame=frame, as_of=self.as_of, time_col=time_col)
        return self

    def add_disclosure_based(
        self,
        name: str,
        frame: pd.DataFrame,
        *,
        disclosed_col: str,
        market: str | None = None,
    ) -> PitContext:
        """開示時刻を「織り込める営業日」に変換して登録する。

        `available_from` 列を生成し、それを時間軸にする。決算日当日に決算内容を
        知っている状態を防ぐための最重要処理。
        """
        work = frame.copy()
        if work.empty:
            work["available_from"] = pd.Series(dtype="object")
        else:
            work["available_from"] = effective_dates(
                work[disclosed_col], market=market or self.market, calendar=self.calendar
            )
        return self.add(name, work, "available_from")

    def get(self, name: str) -> pd.DataFrame:
        if name not in self.inputs:
            raise KeyError(f"input {name!r} not registered: {sorted(self.inputs)}")
        return self.inputs[name].visible

    def optional(self, name: str) -> pd.DataFrame | None:
        """欠けていても計算を続けたい入力用（機能縮退）。"""
        if name not in self.inputs:
            return None
        visible = self.inputs[name].visible
        return None if visible.empty else visible

    def with_as_of(self, as_of: date) -> PitContext:
        return PitContext(
            as_of=as_of,
            market=self.market,
            calendar=self.calendar,
            inputs={k: v.with_as_of(as_of) for k, v in self.inputs.items()},
        )

    def extended_with(self, extra: Mapping[str, pd.DataFrame]) -> PitContext:
        """同じ `as_of` のまま、各入力に追加行を連結した文脈を作る。

        リーク検証専用。`as_of` より後の行を足しても出力が変わらないことを確認する。
        """
        merged: dict[str, PitFrame] = {}
        for name, pit in self.inputs.items():
            addition = extra.get(name)
            frame = (
                pit.frame
                if addition is None or addition.empty
                else pd.concat([pit.frame, addition], ignore_index=True)
            )
            merged[name] = PitFrame(frame=frame, as_of=self.as_of, time_col=pit.time_col)
        return PitContext(
            as_of=self.as_of, market=self.market, calendar=self.calendar, inputs=merged
        )


def _as_date_series(values: pd.Series) -> pd.Series:
    if values.empty:
        return pd.Series([], dtype="object")
    if values.map(lambda v: isinstance(v, date) and not isinstance(v, datetime)).all():
        return values
    converted = pd.to_datetime(values, errors="coerce")
    if getattr(converted.dtype, "tz", None) is not None:
        converted = converted.dt.tz_convert(None)
    return converted.dt.date


def assert_no_future_rows(frame: pd.DataFrame, as_of: date, time_col: str) -> None:
    """`as_of` より後の行が残っていないことを確認する。"""
    if frame.empty:
        return
    times = _as_date_series(frame[time_col])
    future = times.notna() & (times > as_of)
    if bool(future.any()):
        worst = times.loc[future].max()
        raise LeakError(
            f"{int(future.sum())} row(s) after as_of={as_of} remain in {time_col} (max={worst})"
        )


def assert_monotonic_availability(
    frame: pd.DataFrame, *, as_of_col: str = "as_of", available_col: str = "available_from"
) -> None:
    """`available_from <= as_of` を確認する。財務データの割り当て検査。"""
    if frame.empty:
        return
    as_of = _as_date_series(frame[as_of_col])
    available = _as_date_series(frame[available_col])
    bad = available.notna() & as_of.notna() & (available > as_of)
    if bool(bad.any()):
        raise LeakError(
            f"{int(bad.sum())} row(s) reference data published after as_of "
            f"({available_col} > {as_of_col})"
        )


def assert_stable_under_future_data(
    compute: Callable[[PitContext], pd.DataFrame],
    context: PitContext,
    future_rows: Mapping[str, pd.DataFrame],
    *,
    compare_cols: Iterable[str] | None = None,
    label: str = "feature",
) -> pd.DataFrame:
    """未来データを追加しても出力が一致することを検証する。

    add-analysis-factor SKILL のリーク検証の中核。`future_rows` には `as_of` より
    後の日付を持つ行を渡す。差分が出たら、その特徴量はどこかで未来を見ている。

    Returns:
        検証に使った（未来データ無しの）計算結果。
    """
    baseline = compute(context)
    with_future = compute(context.extended_with(future_rows))
    cols = list(compare_cols) if compare_cols is not None else list(baseline.columns)
    left = baseline.reindex(columns=cols).reset_index(drop=True)
    right = with_future.reindex(columns=cols).reset_index(drop=True)
    if left.shape != right.shape:
        raise LeakError(
            f"{label}: output shape changed when future rows were appended "
            f"({left.shape} -> {right.shape})"
        )
    try:
        pd.testing.assert_frame_equal(left, right, check_dtype=False, rtol=1e-12, atol=1e-12)
    except AssertionError as exc:  # pragma: no cover - 差分内容はメッセージに委譲
        raise LeakError(f"{label}: output changed after appending future rows -> {exc}") from exc
    return baseline


def future_rows_like(
    frame: pd.DataFrame,
    *,
    time_col: str,
    as_of: date,
    days: int = 5,
    numeric_multiplier: float = 3.0,
) -> pd.DataFrame:
    """リーク検証用に、`as_of` より後の「極端な」行を合成する。

    値を大きくずらすのは、混入したときに差分として確実に現れるようにするため。
    """
    if frame.empty:
        return frame.copy()
    source = frame.copy()
    source[time_col] = _as_date_series(source[time_col])
    last_day = source[time_col].max()
    anchor = max(last_day, as_of) if last_day is not None else as_of
    tail = source.loc[source[time_col] == anchor]
    if tail.empty:
        tail = source.tail(1)
    out: list[pd.DataFrame] = []
    for offset in range(1, days + 1):
        chunk = tail.copy()
        chunk[time_col] = anchor + pd.Timedelta(days=offset)
        chunk[time_col] = chunk[time_col].map(lambda ts: ts.date() if hasattr(ts, "date") else ts)
        for col in chunk.select_dtypes("number").columns:
            chunk[col] = chunk[col] * numeric_multiplier
        out.append(chunk)
    return pd.concat(out, ignore_index=True)


def latest_available(
    frame: pd.DataFrame,
    *,
    key: str | list[str],
    time_col: str,
    as_of: date,
    tie_breakers: Iterable[str] = (),
) -> pd.DataFrame:
    """銘柄ごとに `as_of` 時点で最新の 1 行を取る。

    財務データを日次特徴量に貼るときの標準手順。同一公開日に複数版（訂正報告など）
    があるときは `tie_breakers` の降順で最後の 1 件を採用する。
    """
    keys = [key] if isinstance(key, str) else list(key)
    if frame.empty:
        return frame.copy()
    work = frame.copy()
    work[time_col] = _as_date_series(work[time_col])
    work = work.loc[work[time_col].notna() & (work[time_col] <= as_of)]
    if work.empty:
        return work
    order = [*keys, time_col, *tie_breakers]
    work = work.sort_values(order, kind="mergesort")
    return work.groupby(keys, as_index=False, sort=False).tail(1).reset_index(drop=True)


def align_asof(
    left: pd.DataFrame,
    right: pd.DataFrame,
    *,
    by: str,
    left_time: str,
    right_time: str,
    suffix: str = "",
    columns: Iterable[str] | None = None,
) -> pd.DataFrame:
    """`right` を「その時点で公開済みの最新値」として `left` に貼る。

    `pd.merge_asof(direction="backward")` を使う。`forward`/`nearest` は未来を
    見るため使ってはいけない。
    """
    if left.empty:
        return left.copy()
    take = list(columns) if columns is not None else [c for c in right.columns if c != right_time]
    lhs = left.copy()
    lhs[left_time] = pd.to_datetime(_as_date_series(lhs[left_time]))
    rhs = right.copy()
    if rhs.empty:
        for col in take:
            if col != by:
                lhs[f"{col}{suffix}"] = pd.NA
        return lhs
    rhs[right_time] = pd.to_datetime(_as_date_series(rhs[right_time]))
    rhs = rhs.loc[:, list(dict.fromkeys([by, right_time, *take]))]
    lhs = lhs.sort_values(left_time, kind="mergesort")
    rhs = rhs.sort_values(right_time, kind="mergesort")
    merged = pd.merge_asof(
        lhs,
        rhs,
        left_on=left_time,
        right_on=right_time,
        by=by,
        direction="backward",
        suffixes=("", suffix or "_r"),
    )
    merged[left_time] = merged[left_time].dt.date
    return merged.reset_index(drop=True)


def describe_pit_inputs(context: PitContext) -> dict[str, Any]:
    """デバッグ用。各入力の可視範囲を要約する。"""
    summary: dict[str, Any] = {"as_of": context.as_of, "market": context.market}
    for name, pit in context.inputs.items():
        visible = pit.visible
        summary[name] = {
            "rows_total": int(len(pit.frame)),
            "rows_visible": int(len(visible)),
            "max_visible": None if visible.empty else max(visible[pit.time_col]),
        }
    return summary
