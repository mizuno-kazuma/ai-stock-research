"""レジーム検出（docs/04-analysis-engine.md §5）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from packages.core.models.regime import (
    correlation_regime,
    feature_drift_ks,
    model_degradation,
    vol_regime_from_levels,
)


def test_vol_regime_flags_high_percentile() -> None:
    rng = np.random.default_rng(0)
    n = 400
    calm = 100 * np.exp(np.cumsum(rng.normal(0, 0.005, n)))
    shock = calm.copy()
    shock[-5:] = shock[-6] * np.array([1.08, 0.90, 1.10, 0.88, 1.12])
    levels = pd.Series(shock, index=pd.bdate_range("2024-01-02", periods=n))
    result = vol_regime_from_levels(levels)
    assert result.percentile is not None
    assert result.percentile >= 0.80
    assert result.high_vol is True
    assert result.level == "high"


def test_vol_regime_unknown_when_short() -> None:
    levels = pd.Series([100.0, 101.0, 99.0])
    result = vol_regime_from_levels(levels)
    assert result.level == "unknown"
    assert result.high_vol is False


def test_correlation_regime_high_when_series_move_together() -> None:
    idx = pd.bdate_range("2025-01-02", periods=80)
    base = np.linspace(100, 120, 80)
    frame = pd.DataFrame(
        {
            "trade_date": list(idx) * 4,
            "ticker": ["A"] * 80 + ["B"] * 80 + ["C"] * 80 + ["D"] * 80,
            "close": list(base)
            + list(base * 1.01)
            + list(base * 0.99)
            + list(base * 1.02),
        }
    )
    result = correlation_regime(frame)
    assert result.avg_pairwise_corr_60d is not None
    assert result.avg_pairwise_corr_60d > 0.8
    assert result.level == "high"


def test_model_degradation_when_recent_ic_in_bottom_decile() -> None:
    good = pd.Series(np.full(240, 0.04))
    bad = pd.Series(np.full(20, -0.05))
    ics = pd.concat([good, bad], ignore_index=True)
    result = model_degradation(ics)
    assert result.degraded is True
    assert result.rank_ic_20d is not None
    assert result.rank_ic_20d < 0


def test_feature_drift_ks_recommends_retrain() -> None:
    rng = np.random.default_rng(1)
    train = pd.DataFrame(
        {
            "mom_20": rng.normal(0, 1, 200),
            "per": rng.normal(15, 2, 200),
            "roe": rng.normal(0.1, 0.02, 200),
        }
    )
    recent = pd.DataFrame(
        {
            "mom_20": rng.normal(3, 1, 80),
            "per": rng.normal(40, 2, 80),
            "roe": rng.normal(0.4, 0.02, 80),
        }
    )
    result = feature_drift_ks(train, recent)
    assert result.n_drifted >= 3
    assert result.retrain_recommended is True
