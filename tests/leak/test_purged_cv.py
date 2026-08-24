"""T-LEAK-03: PurgedWalkForwardCV の分割が正しいこと。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from packages.core.models.cv import PurgedWalkForwardCV


def test_purged_cv_no_overlap_between_train_and_test() -> None:
    dates = pd.bdate_range("2024-01-01", "2026-08-01")
    groups = np.repeat(dates.date, 20)
    cv = PurgedWalkForwardCV(
        n_splits=5,
        label_horizon_days=20,
        embargo_days=5,
        test_days=60,
        min_train_days=200,
    )
    X = np.zeros(len(groups))
    n = 0
    for train_idx, test_idx in cv.split(X=X, groups=groups):
        n += 1
        train_max = groups[train_idx].max()
        test_min = groups[test_idx].min()
        gap_bdays = np.busday_count(train_max, test_min)
        assert gap_bdays >= 20 + 5, f"purge(20)+embargo(5) の間隔が不足: {gap_bdays}"
        assert len(set(train_idx) & set(test_idx)) == 0
        assert train_max < test_min
    assert n >= 1


def test_purged_cv_rejects_missing_groups() -> None:
    cv = PurgedWalkForwardCV(min_train_days=10, test_days=5, n_splits=2)
    with pytest.raises(ValueError, match="groups"):
        list(cv.split(X=np.zeros(100), groups=None))
