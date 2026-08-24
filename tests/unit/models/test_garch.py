"""T-STAT-03: GARCH の収束と定常性、フォールバック。"""

from __future__ import annotations

import numpy as np
import pytest

from packages.core.models.errors import GarchConvergenceError, GarchNonStationaryError
from packages.core.models.garch import compute_vol_features, fit_garch


def _garch_series(n: int, alpha: float, beta: float, omega: float = 0.05, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    r = np.zeros(n)
    var = omega / max(1.0 - alpha - beta, 1e-6)
    for t in range(n):
        r[t] = rng.normal(scale=np.sqrt(max(var, 1e-8)))
        var = omega + alpha * r[t] ** 2 + beta * var
    return r


def integrated_garch_series(n: int = 1000, seed: int = 3) -> np.ndarray:
    return _garch_series(n, alpha=0.15, beta=0.85, omega=1e-8, seed=seed)


def test_garch_raises_on_nonstationary() -> None:
    series = integrated_garch_series(n=1000)
    with pytest.raises((GarchNonStationaryError, GarchConvergenceError)):
        fit_garch(series)


def test_garch_returns_point_and_interval() -> None:
    series = _garch_series(600, alpha=0.05, beta=0.90, seed=1)
    result = fit_garch(series)
    assert result.vol_1d_ann > 0
    assert result.vol_1d_ann_lo <= result.vol_1d_ann <= result.vol_1d_ann_hi
    assert result.ret_1d_lo < result.ret_1d < result.ret_1d_hi
    assert result.persistence < 0.999


def test_garch_falls_back_to_realized_vol() -> None:
    series = np.zeros(80)
    result = compute_vol_features(series, realized_vol_20d=0.2, realized_vol_60d=0.18)
    assert result["garch_vol_20d"] is None
    assert result["realized_vol_60d"] == 0.18
    assert "GARCH_FALLBACK" in result["quality_flags"]
