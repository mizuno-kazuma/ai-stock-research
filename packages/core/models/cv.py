"""Purged Walk-Forward CV（docs/04-analysis-engine.md §3.3）。

唯一許可する検証手法。KFold / TimeSeriesSplit / train_test_split は
時系列ラベルの重なりを防げないため禁止（T-LEAK-01）。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import numpy as np
import pandas as pd


class PurgedWalkForwardCV:
    """時系列の Walk-Forward 分割。

    学習末尾からラベル期間分を purge し、さらに embargo を空けて test を開始する。

        [--------- train ---------][purge][embargo][--- test ---]

    `groups`（as_of 日付）なしでの分割は許可しない。
    """

    def __init__(
        self,
        n_splits: int = 6,
        label_horizon_days: int | None = None,
        embargo_days: int = 5,
        test_days: int | None = None,
        min_train_days: int = 504,
        *,
        purge_days: int | None = None,
        test_window_days: int | None = None,
        train_window_days: int | None = None,
        expanding: bool = True,
    ) -> None:
        if n_splits < 1:
            raise ValueError("n_splits は 1 以上である必要があります")
        self.n_splits = int(n_splits)
        self.label_horizon_days = int(
            purge_days if purge_days is not None else (label_horizon_days or 20)
        )
        self.embargo_days = int(embargo_days)
        self.test_days = int(
            test_window_days if test_window_days is not None else (test_days or 60)
        )
        self.min_train_days = int(min_train_days)
        self.train_window_days = (
            int(train_window_days) if train_window_days is not None else None
        )
        self.expanding = bool(expanding)

    def get_n_splits(self, X=None, y=None, groups=None) -> int:  # noqa: ANN001
        return self.n_splits

    def split(
        self,
        X,  # noqa: ANN001
        y=None,  # noqa: ANN001
        groups=None,  # noqa: ANN001
    ) -> Iterator[tuple[np.ndarray, np.ndarray]]:
        if groups is None:
            raise ValueError(
                "groups（as_of日付）は必須。日付なしの分割を許可しない。"
                "PurgedWalkForwardCV を使ってください。"
            )
        groups_arr = _as_date_array(groups)
        if len(groups_arr) != _length(X):
            raise ValueError(
                f"groups の長さ ({len(groups_arr)}) が X ({_length(X)}) と一致しません"
            )

        unique_dates = np.array(sorted(pd.unique(groups_arr)))
        n_dates = len(unique_dates)
        produced = 0
        # 末尾の test から過去へ向かって切る（仕様の疑似コードに合わせる）。
        for i in range(self.n_splits):
            test_end = n_dates - i * self.test_days
            test_start = test_end - self.test_days
            if test_start < 0 or test_end <= 0:
                break
            purge_end = test_start - self.embargo_days
            train_end = purge_end - self.label_horizon_days
            if train_end < self.min_train_days:
                break
            if train_end <= 0:
                break
            train_start = 0
            if not self.expanding and self.train_window_days is not None:
                train_start = max(0, train_end - self.train_window_days)
                if train_end - train_start < self.min_train_days:
                    break
            train_dates = unique_dates[train_start:train_end]
            test_dates = unique_dates[test_start:test_end]
            if len(train_dates) == 0 or len(test_dates) == 0:
                break
            train_idx = np.flatnonzero(np.isin(groups_arr, train_dates))
            test_idx = np.flatnonzero(np.isin(groups_arr, test_dates))
            if len(train_idx) == 0 or len(test_idx) == 0:
                break
            yield train_idx, test_idx
            produced += 1
        if produced == 0:
            raise ValueError(
                "有効な Walk-Forward 分割を作れませんでした。"
                "履歴が短すぎるか、min_train_days / purge / embargo が大きすぎます。"
            )


def _length(X: object) -> int:
    if X is None:
        raise ValueError("X は必須です")
    if hasattr(X, "__len__"):
        return len(X)  # type: ignore[arg-type]
    raise TypeError(f"長さを取れません: {type(X)!r}")


def _as_date_array(groups: object) -> np.ndarray:
    series = pd.Series(groups)
    if pd.api.types.is_datetime64_any_dtype(series):
        return series.dt.date.to_numpy()
    converted = pd.to_datetime(series, errors="coerce")
    if converted.notna().all() and not (
        series.dtype == object and series.map(lambda v: isinstance(v, date)).all()
    ):
        # 文字列や Timestamp は date に揃える。すでに date ならそのまま。
        if not series.map(lambda v: isinstance(v, date)).all():
            return converted.dt.date.to_numpy()
    return np.array(series.to_list(), dtype=object)
