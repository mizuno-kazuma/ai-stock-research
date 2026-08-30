"""日次 Analyst の為替経路に ARIMAX と Diebold-Mariano を載せる。"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from services.agent.jobs.analyst import analyst
from tests.fakes import FakeStateRepo, FakeWarehouse


def _mark_collector_ok(state: FakeStateRepo, *, market: str = "JP") -> None:
    state.create_job_run(job_name="collector", market=market)
    state.record_job_run(max(state._runs), status="success")


def _prices(as_of: date, *, n: int = 40) -> pd.DataFrame:
    days = pd.bdate_range(end=as_of, periods=n)
    return pd.DataFrame(
        {
            "ticker": ["7203"] * len(days),
            "market": ["JP"] * len(days),
            "trade_date": [d.date() for d in days],
            "adj_close": np.linspace(100.0, 110.0, len(days)),
            "adj_open": np.linspace(100.0, 110.0, len(days)),
            "volume": [1_000_000] * len(days),
        }
    )


def _macro_row(series_id: str, day: date, value: float) -> dict[str, object]:
    return {
        "series_id": series_id,
        "observation_date": day,
        "vintage_date": day,
        "value": float(value),
    }


def test_analyst_fx_writes_baseline_arimax_and_dm() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    as_of = date(2026, 8, 21)
    _mark_collector_ok(state)
    warehouse.prices = _prices(as_of)

    n = 140
    dates = pd.bdate_range(end=as_of, periods=n)
    rng = np.random.default_rng(2)
    spot = 150.0 + np.cumsum(rng.normal(0.02, 0.25, n))
    dgs10 = 4.0 + np.cumsum(rng.normal(0.0, 0.02, n))
    jp10 = 0.6 + np.cumsum(rng.normal(0.0, 0.005, n))
    rows: list[dict[str, object]] = []
    for day_ts, s, u, j in zip(dates, spot, dgs10, jp10, strict=True):
        day = day_ts.date()
        rows.append(_macro_row("DEXJPUS", day, s))
        rows.append(_macro_row("DGS10", day, u))
        rows.append(_macro_row("IRLTLT01JPM156N", day, j))
    warehouse.macro_rows = rows

    result = analyst("JP", as_of, state=state, warehouse=warehouse)
    assert result.steps["fx"].status == "success"
    models = {r["model_id"] for r in warehouse.fx_rows}
    assert "random_walk" in models
    assert "arimax" in models
    rw = next(r for r in warehouse.fx_rows if r["model_id"] == "random_walk")
    arimax = next(r for r in warehouse.fx_rows if r["model_id"] == "arimax")
    assert rw["is_baseline"] is True
    assert arimax["is_baseline"] is False
    assert arimax["n_validation"] is not None
    assert int(arimax["n_validation"]) >= 8
    assert arimax["dm_statistic"] is not None
    assert arimax["dm_pvalue"] is not None
    # 非有意なら優位性を捏造しない
    if float(arimax["dm_pvalue"]) >= 0.05:
        assert arimax["beats_baseline"] is False


def test_analyst_fx_short_series_skips_without_failing() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    as_of = date(2026, 8, 21)
    _mark_collector_ok(state)
    warehouse.prices = _prices(as_of, n=30)
    dates = pd.bdate_range(end=as_of, periods=10)
    warehouse.macro_rows = [
        _macro_row("DEXJPUS", d.date(), 150.0 + i * 0.1) for i, d in enumerate(dates)
    ]

    result = analyst("JP", as_of, state=state, warehouse=warehouse)
    assert result.steps["fx"].status == "skipped"
    assert result.steps["fx"].metrics.get("reason") == "too_short"
    assert result.status != "failed"
    assert warehouse.fx_rows == []
    if result.status == "partial":
        assert "fx" not in (result.metrics.get("failed_steps") or [])
