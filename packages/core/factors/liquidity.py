"""流動性系の特徴量（docs/04-analysis-engine.md §1.5）。

流動性はスコアの構成要素というより**ユニバースフィルタ**として使う。個人の資金
規模でも `adv_20d` が小さい銘柄はスリッページで優位性が消える。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from packages.core.factors.panel import PricePanel, require_history

#: `amihud_illiq` は生の値が極端に小さいためスケール調整する（docs §1.5）。
AMIHUD_SCALE = 1e9


def compute_liquidity(
    panel: PricePanel, *, market_cap: pd.Series | None = None
) -> pd.DataFrame:
    if panel.is_empty:
        return pd.DataFrame(index=pd.Index([], name="ticker"))
    lengths = panel.history_length()
    out = pd.DataFrame(index=pd.Index(panel.close.columns, name="ticker"))

    turnover = panel.get("turnover_value")
    if turnover.isna().all().all():
        # `turnover_value` が無いソース（yfinance）では close * volume で近似する。
        turnover = panel.close * panel.get("volume")
    tail = turnover.tail(20)
    counts = tail.notna().sum(axis=0)
    adv = tail.mean(axis=0, skipna=True).where(counts >= 10)
    out["adv_20d"] = require_history(adv, lengths, 20)

    if market_cap is not None and not market_cap.empty:
        caps = pd.to_numeric(market_cap.reindex(out.index), errors="coerce")
        latest_turnover = turnover.iloc[-1]
        out["turnover_ratio"] = latest_turnover / caps.where(caps > 0)
    else:
        out["turnover_ratio"] = np.nan

    ret_1d = panel.simple_returns.tail(20).abs()
    illiq = (ret_1d / turnover.tail(20).where(lambda x: x > 0)).mean(
        axis=0, skipna=True
    ) * AMIHUD_SCALE
    out["amihud_illiq"] = require_history(illiq, lengths, 20)
    return out
