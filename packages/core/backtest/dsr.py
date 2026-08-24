"""Deflated Sharpe Ratio（docs/04-analysis-engine.md §4.4）。

複数の戦略・パラメータを試すと、偶然に高いシャープレシオを持つものが
必ず見つかる。DSR はこのバイアスを補正する。`n_trials` を隠すと判定できない。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from packages.core.models._norm import norm_cdf, norm_ppf

EULER_GAMMA = 0.5772156649015329


@dataclass(frozen=True, slots=True)
class DSRResult:
    dsr: float
    expected_max_sr: float
    sr_std: float
    is_significant: bool
    p_value: float

    @property
    def dsr_pvalue(self) -> float:
        """UI / backtest_runs 向け。1 - DSR が「偶然である確率」に相当。"""
        return self.p_value


def deflated_sharpe_ratio(
    sr_observed: float,
    n_trials: int,
    n_obs: int,
    skew: float,
    kurtosis: float,
    sr_variance_across_trials: float,
    *,
    significance: float = 0.95,
) -> DSRResult:
    if n_trials < 1:
        raise ValueError("n_trials は 1 以上である必要があります")
    if n_obs < 3:
        raise ValueError("n_obs が小さすぎます")
    if sr_variance_across_trials < 0:
        raise ValueError("sr_variance_across_trials は非負である必要があります")

    sr_expected_max = _expected_max_sr(n_trials, sr_variance_across_trials)
    non_norm = (
        1.0
        - skew * sr_observed
        + ((kurtosis - 1.0) / 4.0) * sr_observed**2
    )
    # 非正規性補正が負になると分散が壊れるので床を置く。
    non_norm = max(non_norm, 1e-12)
    sr_std = math.sqrt(non_norm / (n_obs - 1))
    if sr_std <= 0:
        dsr = 0.0
    else:
        dsr = float(norm_cdf((sr_observed - sr_expected_max) / sr_std))
    return DSRResult(
        dsr=dsr,
        expected_max_sr=sr_expected_max,
        sr_std=sr_std,
        is_significant=dsr > significance,
        p_value=float(1.0 - dsr),
    )


def _expected_max_sr(n_trials: int, sr_variance: float) -> float:
    if n_trials <= 1:
        return 0.0
    sigma = math.sqrt(sr_variance) if sr_variance > 0 else 0.0
    if sigma == 0.0:
        return 0.0
    e = EULER_GAMMA
    # n_trials=1 は上で除外済み。ppf(1-1/n) は n>=2 で有限。
    term = (1.0 - e) * norm_ppf(1.0 - 1.0 / n_trials) + e * norm_ppf(
        1.0 - 1.0 / (n_trials * math.e)
    )
    return sigma * term
