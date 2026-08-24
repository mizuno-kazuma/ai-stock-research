"""T-STAT-01: Diebold-Mariano 検定。"""

from __future__ import annotations

import numpy as np

from packages.core.models.arimax import diebold_mariano, naive_dm_pvalue


def test_dm_test_detects_no_difference_for_identical_errors() -> None:
    e = np.random.default_rng(0).normal(size=200)
    r = diebold_mariano(e, e.copy(), h=5)
    assert r.pvalue > 0.99


def test_dm_test_detects_clear_superiority() -> None:
    rng = np.random.default_rng(0)
    e_good = rng.normal(scale=1.0, size=300)
    e_bad = rng.normal(scale=2.0, size=300)
    r = diebold_mariano(e_good, e_bad, h=1)
    assert r.pvalue < 0.01
    assert r.better == "model"
    assert r.beats_baseline


def _ar1_errors(rho: float, n: int, scale: float = 1.0, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    e = np.zeros(n)
    shock = rng.normal(scale=scale, size=n)
    for i in range(1, n):
        e[i] = rho * e[i - 1] + shock[i]
    return e


def test_dm_test_uses_hac_variance_for_multistep() -> None:
    e1 = _ar1_errors(0.7, 300, seed=1)
    e2 = _ar1_errors(0.7, 300, scale=1.05, seed=2)
    p_hac = diebold_mariano(e1, e2, h=20).pvalue
    p_naive = naive_dm_pvalue(e1, e2)
    assert p_hac > p_naive
