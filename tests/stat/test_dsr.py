"""T-STAT-02: Deflated Sharpe Ratio の既知性質。"""

from __future__ import annotations

from packages.core.backtest.dsr import deflated_sharpe_ratio


def test_dsr_decreases_with_more_trials() -> None:
    base = dict(
        sr_observed=1.5,
        n_obs=500,
        skew=-0.2,
        kurtosis=4.0,
        sr_variance_across_trials=0.25,
    )
    dsr_10 = deflated_sharpe_ratio(**base, n_trials=10).dsr
    dsr_1000 = deflated_sharpe_ratio(**base, n_trials=1000).dsr
    assert dsr_1000 < dsr_10


def test_dsr_flags_insignificant_result() -> None:
    r = deflated_sharpe_ratio(
        sr_observed=1.2,
        n_trials=5000,
        n_obs=250,
        skew=0.0,
        kurtosis=3.0,
        sr_variance_across_trials=0.5,
    )
    assert not r.is_significant
    assert r.p_value >= 0.05


def test_dsr_n_trials_one_does_not_explode() -> None:
    r = deflated_sharpe_ratio(
        sr_observed=0.62,
        n_trials=1,
        n_obs=500,
        skew=0.0,
        kurtosis=3.0,
        sr_variance_across_trials=0.25,
    )
    assert 0.0 <= r.dsr <= 1.0
    assert r.expected_max_sr == 0.0
