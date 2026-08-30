"""為替予測は点推定 + 信頼区間。外生欠損時は RW のみ。"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from packages.core.models.arimax import forecast_fx, random_walk_forecast


def test_random_walk_has_interval() -> None:
    fc = random_walk_forecast(150.0, sigma_daily=0.5, horizon=5)
    assert fc.point == 150.0
    assert fc.lo < fc.point < fc.hi


def test_fx_falls_back_to_rw_without_exog() -> None:
    spot = pd.Series(150 + np.cumsum(np.random.default_rng(0).normal(0, 0.3, size=80)))
    bundle = forecast_fx(as_of=date(2026, 8, 1), spot=spot, exog=None, horizon=5)
    assert bundle.random_walk.lo < bundle.random_walk.point < bundle.random_walk.hi
    assert bundle.arimax is None
    rows = bundle.as_rows()
    assert any(r["model_id"] == "random_walk" for r in rows)
    assert all("point_forecast" in r for r in rows)
    assert all(r["ci_lo_80"] < r["ci_hi_80"] for r in rows)
    assert all(r["ci_lo_95"] <= r["ci_lo_80"] for r in rows)
    assert all(r["ci_hi_95"] >= r["ci_hi_80"] for r in rows)


def test_fx_arimax_and_dm_with_exog() -> None:
    idx = pd.bdate_range("2024-01-02", periods=130)
    rng = np.random.default_rng(3)
    spot = pd.Series(150 + np.cumsum(rng.normal(0.02, 0.25, 130)), index=idx)
    exog = pd.DataFrame(
        {"rate_diff_10y": 3.5 + np.cumsum(rng.normal(0.0, 0.02, 130))},
        index=idx,
    )
    bundle = forecast_fx(as_of=date(2026, 8, 1), spot=spot, exog=exog, horizon=5)
    assert bundle.arimax is not None
    assert bundle.n_validation is not None and bundle.n_validation >= 8
    assert bundle.dm is not None
    rows = {r["model_id"]: r for r in bundle.as_rows()}
    assert "random_walk" in rows and "arimax" in rows
    assert rows["arimax"]["n_validation"] == bundle.n_validation
    if bundle.dm.pvalue >= 0.05:
        assert rows["arimax"]["beats_baseline"] is False
