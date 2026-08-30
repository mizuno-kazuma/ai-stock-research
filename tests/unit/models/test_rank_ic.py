"""Rank IC の t 統計と model_retrain への記録（F06）。"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from packages.core.models.ranker import evaluate_rank_ic
from services.agent.jobs.maintenance import model_retrain
from tests.fakes import FakeStateRepo, FakeWarehouse


def test_evaluate_rank_ic_computes_t_stat_from_daily_series() -> None:
    rng = np.random.default_rng(0)
    days = [date(2026, 6, 1) + timedelta(days=i) for i in range(12)]
    pred = []
    realized = []
    groups = []
    for day in days:
        x = rng.normal(size=8)
        pred.extend(x.tolist())
        realized.extend((0.4 * x + rng.normal(scale=0.3, size=8)).tolist())
        groups.extend([day] * 8)
    out = evaluate_rank_ic(pd.Series(pred), pd.Series(realized), groups=pd.Series(groups))
    assert out["rank_ic"] == out["rank_ic"]
    assert out["t_stat"] == out["t_stat"]
    assert abs(out["t_stat"]) > 0


def _synthetic_panel(*, n_tickers: int = 6, n_days: int = 55) -> tuple[pd.DataFrame, pd.DataFrame]:
    start = date(2026, 4, 1)
    dates = [start + timedelta(days=i) for i in range(n_days + 30)]
    tickers = [f"T{i:03d}" for i in range(n_tickers)]
    prices = []
    features = []
    rng = np.random.default_rng(1)
    level = {t: 100.0 + i for i, t in enumerate(tickers)}
    for i, day in enumerate(dates):
        for t in tickers:
            shock = float(rng.normal(scale=0.8))
            level[t] = max(10.0, level[t] * (1.0 + shock / 100.0))
            px = level[t]
            prices.append(
                {
                    "ticker": t,
                    "market": "JP",
                    "trade_date": day,
                    "adj_open": px,
                    "adj_close": px,
                    "close": px,
                }
            )
            if i < n_days:
                features.append(
                    {
                        "ticker": t,
                        "market": "JP",
                        "as_of": day,
                        "feature_version": "v1",
                        "mom_12_1": float(rng.normal()),
                        "realized_vol_60d": 0.2 + float(rng.random()) * 0.05,
                    }
                )
    return pd.DataFrame(features), pd.DataFrame(prices)


def test_model_retrain_writes_fold_rank_ic() -> None:
    features, prices = _synthetic_panel()
    warehouse = FakeWarehouse()
    warehouse.features = features
    warehouse.prices = prices
    as_of = date(2026, 7, 1)
    result = model_retrain(
        "JP",
        as_of,
        state=FakeStateRepo(),
        warehouse=warehouse,
        n_trials=1,
    )
    assert result.status == "success"
    assert warehouse.model_runs
    row = warehouse.model_runs[-1]
    folds = list(row.get("fold_rank_ic") or [])
    assert folds
    assert all(isinstance(x, float) for x in folds)
    assert row.get("n_trials") == 1
    assert row.get("n_folds") == len(folds)
