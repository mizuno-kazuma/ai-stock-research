"""取引コスト。手数料・スリッページ・回転率上限にデフォルト値を持たせない。"""

from __future__ import annotations

import numpy as np


def participation_slippage_bps(
    order_value: float, adv_20d: float, base_bps: float
) -> float:
    """注文サイズが平均売買代金に対して大きいほどスリッページが増える。

    平方根モデル（市場インパクトの標準的な近似）。
    """
    participation = order_value / max(float(adv_20d), 1.0)
    return float(base_bps) * (1.0 + 3.0 * np.sqrt(max(participation, 0.0)))


def round_trip_cost_bps(
    *,
    fee_bps: float,
    slippage_bps: float,
    order_value: float | None = None,
    adv_20d: float | None = None,
) -> float:
    """往復コスト（bps）。スリッページは片道、手数料は往復で 2 回。"""
    slip = float(slippage_bps)
    if order_value is not None and adv_20d is not None:
        slip = participation_slippage_bps(order_value, adv_20d, slip)
    return 2.0 * float(fee_bps) + 2.0 * slip
