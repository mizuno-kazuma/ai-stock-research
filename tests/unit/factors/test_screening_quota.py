"""推奨件数の目標補充（docs/05-scoring-screening.md §7.2）。"""

from __future__ import annotations

import pandas as pd

from packages.core.factors.scoring import is_candidate
from packages.core.factors.screening import (
    apply_risk_constraints,
    select_recommendation_candidates,
)


def _row(
    ticker: str,
    *,
    total_score: float,
    quant_percentile: float,
    ml_pred_h20: float,
    ml_pred_h20_lo: float,
    sector: str,
) -> dict[str, object]:
    return {
        "ticker": ticker,
        "total_score": total_score,
        "quant_score": total_score,
        "quant_percentile": quant_percentile,
        "ml_pred_h20": ml_pred_h20,
        "ml_pred_h20_lo": ml_pred_h20_lo,
        "ml_pred_h20_hi": 0.10,
        "sector_code": sector,
        "n_missing": 0,
    }


def test_select_fills_quota_when_one_core_candidate() -> None:
    rows = [
        _row(
            "CORE",
            total_score=61.0,
            quant_percentile=0.92,
            ml_pred_h20=0.04,
            ml_pred_h20_lo=-0.01,
            sector="S99",
        )
    ]
    for i in range(12):
        rows.append(
            _row(
                f"F{i:02d}",
                total_score=80.0 - i,
                quant_percentile=0.70,
                ml_pred_h20=-0.01,
                ml_pred_h20_lo=-0.12,
                sector=f"S{i % 4:02d}",
            )
        )
    selected = select_recommendation_candidates(pd.DataFrame(rows), max_per_day=10)
    assert len(selected) == 10
    assert (selected["candidate_tier"] == "core").sum() == 1
    assert selected.iloc[0]["ticker"] == "CORE"
    assert (selected["candidate_tier"] == "fill").sum() == 9


def test_fill_does_not_displace_core_candidate() -> None:
    rows = [
        _row(
            "CORE",
            total_score=55.0,
            quant_percentile=0.90,
            ml_pred_h20=0.03,
            ml_pred_h20_lo=-0.02,
            sector="S99",
        ),
        _row(
            "HOT",
            total_score=99.0,
            quant_percentile=0.99,
            ml_pred_h20=-0.02,
            ml_pred_h20_lo=-0.15,
            sector="S01",
        ),
    ]
    selected = select_recommendation_candidates(pd.DataFrame(rows), max_per_day=10)
    tickers = list(selected["ticker"])
    assert tickers[0] == "CORE"
    assert "HOT" in tickers
    assert selected.loc[selected["ticker"] == "CORE", "candidate_tier"].iloc[0] == "core"
    assert selected.loc[selected["ticker"] == "HOT", "candidate_tier"].iloc[0] == "fill"


def test_fill_respects_sector_cap_including_core() -> None:
    rows = [
        _row(
            "CORE",
            total_score=70.0,
            quant_percentile=0.91,
            ml_pred_h20=0.05,
            ml_pred_h20_lo=-0.01,
            sector="S01",
        )
    ]
    for i in range(8):
        rows.append(
            _row(
                f"S01F{i}",
                total_score=90.0 - i,
                quant_percentile=0.60,
                ml_pred_h20=-0.01,
                ml_pred_h20_lo=-0.10,
                sector="S01",
            )
        )
    for i in range(8):
        rows.append(
            _row(
                f"S02F{i}",
                total_score=50.0 - i,
                quant_percentile=0.55,
                ml_pred_h20=-0.01,
                ml_pred_h20_lo=-0.10,
                sector="S02",
            )
        )
    for i in range(8):
        rows.append(
            _row(
                f"S03F{i}",
                total_score=40.0 - i,
                quant_percentile=0.52,
                ml_pred_h20=-0.01,
                ml_pred_h20_lo=-0.10,
                sector="S03",
            )
        )
    for i in range(8):
        rows.append(
            _row(
                f"S04F{i}",
                total_score=30.0 - i,
                quant_percentile=0.51,
                ml_pred_h20=-0.01,
                ml_pred_h20_lo=-0.10,
                sector="S04",
            )
        )
    selected = select_recommendation_candidates(pd.DataFrame(rows), max_per_day=10)
    assert len(selected) == 10
    s01 = selected.loc[selected["sector_code"] == "S01"]
    assert len(s01) == 3
    assert "CORE" in set(s01["ticker"])


def test_empty_work_returns_empty() -> None:
    selected = select_recommendation_candidates(pd.DataFrame(), max_per_day=10)
    assert selected.empty


def test_apply_risk_constraints_still_caps_to_max() -> None:
    rows = [
        _row(
            f"T{i}",
            total_score=float(90 - i),
            quant_percentile=0.9,
            ml_pred_h20=0.04,
            ml_pred_h20_lo=-0.01,
            sector=f"S{i}",
        )
        for i in range(15)
    ]
    taken = apply_risk_constraints(pd.DataFrame(rows), max_per_day=10)
    assert len(taken) == 10


def test_is_candidate_unchanged_strict_gate() -> None:
    core = pd.Series(
        {
            "quant_percentile": 0.85,
            "ml_pred_h20": 0.001,
            "ml_pred_h20_lo": -0.049,
        }
    )
    fail_lo = pd.Series(
        {
            "quant_percentile": 0.99,
            "ml_pred_h20": 0.04,
            "ml_pred_h20_lo": -0.05,
        }
    )
    assert is_candidate(core) is True
    assert is_candidate(fail_lo) is False
