"""ランカーは点推定 + q20/q80。n_trials 必須。"""

from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest

from packages.core.models.ranker import train_ranker


def test_train_ranker_requires_n_trials() -> None:
    sig = inspect.signature(train_ranker)
    assert sig.parameters["n_trials"].default is inspect.Parameter.empty
    assert sig.parameters["n_trials"].kind == inspect.Parameter.KEYWORD_ONLY


def test_ranker_emits_confidence_interval() -> None:
    rng = np.random.default_rng(0)
    n = 80
    X = pd.DataFrame({"f1": rng.normal(size=n), "f2": rng.normal(size=n)})
    y = 0.1 * X["f1"] + rng.normal(scale=0.05, size=n)
    model = train_ranker(X, y, n_trials=1, feature_cols=["f1", "f2"])
    pred = model.predict(X)
    assert (pred["ml_pred_lo"] <= pred["ml_pred"]).all()
    assert (pred["ml_pred"] <= pred["ml_pred_hi"]).all()
    assert model.n_trials == 1


def test_ols_does_not_zero_fill_missing_features() -> None:
    """欠損を 0 埋めすると平均的な信号になる。推論では NaN を残す。"""
    rng = np.random.default_rng(1)
    n = 80
    X = pd.DataFrame({"f1": rng.normal(size=n), "f2": rng.normal(size=n)})
    y = 0.2 * X["f1"] - 0.1 * X["f2"]
    model = train_ranker(X, y, n_trials=1, feature_cols=["f1", "f2"])
    assert model.backend == "ols"
    infer = pd.DataFrame({"f1": [1.0, np.nan], "f2": [0.5, 0.5]})
    pred = model.predict(infer)
    assert np.isfinite(pred.loc[0, "ml_pred"])
    assert not np.isfinite(pred.loc[1, "ml_pred"])


def test_ranker_rejects_too_many_trials() -> None:
    X = pd.DataFrame({"f1": [1.0] * 60, "f2": [0.0] * 60})
    y = pd.Series([0.0] * 60)
    with pytest.raises(ValueError, match="上限"):
        train_ranker(X, y, n_trials=51, feature_cols=["f1", "f2"])
