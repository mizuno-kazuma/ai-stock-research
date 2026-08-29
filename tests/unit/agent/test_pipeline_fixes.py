"""本番パイプラインを止めていた欠陥の回帰テスト。"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from packages.core.models.ranker import (
    FittedRanker,
    load_fitted_ranker,
    ranker_artifact_path,
    save_fitted_ranker,
)
from packages.core.storage import DuckDBRepo
from services.agent.jobs.analyst import analyst
from services.agent.jobs.collector import COLLECTOR_STEPS, collector
from services.agent.jobs.strategist import build_recommendation, strategist
from services.agent.pipeline import run_pipeline
from services.agent.wiring import pipeline_dependencies, try_load_ranker
from tests.fakes import FakeStateRepo, FakeWarehouse
from tests.unit.agent.test_agent_loop import _ok_prices_step, _score_frame


def _ok(_market: str, _as_of: date) -> dict:
    return {"rows": 1}


def test_upsert_features_accepts_nan_in_integer_column() -> None:
    duck = DuckDBRepo.in_memory()
    duck.init_db()
    n = duck.upsert_features_daily(
        [
            {
                "ticker": "7203",
                "market": "JP",
                "as_of": date(2026, 8, 27),
                "currency": "JPY",
                "feature_version": "v1.0.0",
                "n_missing": 3,
                "forecast_revision_direction": np.nan,
            }
        ]
    )
    assert n == 1
    row = duck.get_features("7203", "JP", date(2026, 8, 27))
    assert row is not None
    assert row["forecast_revision_direction"] is None


def test_build_recommendation_fills_interval_without_ml() -> None:
    row = pd.Series(
        {
            "ticker": "7203",
            "quant_score": 80,
            "total_score": 80,
            "ml_pred_h20": np.nan,
            "ml_pred_h20_lo": np.nan,
            "ml_pred_h20_hi": np.nan,
            "realized_vol_60d": 0.25,
            "qual_score": None,
        }
    )
    rec = build_recommendation(
        row,
        as_of=date(2026, 8, 21),
        market="JP",
        n_prior_samples=8,
        hit_rate_prior=None,
        thesis=None,
        memory_ids=[],
        source_doc_ids=["quant:scores_daily"],
        data_freshness=[],
    )
    assert rec["expected_ret_lo"] is not None
    assert rec["expected_ret_hi"] is not None
    assert rec["expected_ret_hi"] > rec["expected_ret_lo"]
    assert rec["conviction"] == "low"


def test_pipeline_completes_when_ml_interval_missing() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    as_of = date(2026, 8, 21)
    scores = _score_frame(as_of).copy()
    scores["ml_pred_h20"] = np.nan
    scores["ml_pred_h20_lo"] = np.nan
    scores["ml_pred_h20_hi"] = np.nan
    warehouse.scores = scores
    warehouse.doc_text["quant:scores_daily"] = "定量スコアとML予測区間に基づく自動生成カードです。"
    warehouse.documents["quant:scores_daily"] = {
        "doc_id": "quant:scores_daily",
        "filed_at": datetime(2026, 8, 20),
        "ticker": "7203",
    }
    result = run_pipeline(
        "JP",
        as_of,
        state=state,
        warehouse=warehouse,
        collector_steps={"prices": _ok_prices_step},
        scores=scores,
    )
    assert result.status != "failed"
    assert "critic" in result.jobs
    assert "evaluator" in result.jobs
    assert len(warehouse.recs) > 0
    assert warehouse.recs[0]["expected_ret_lo"] is not None


def test_strategist_discards_invariant_violation_without_raising() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    as_of = date(2026, 8, 21)
    scores = _score_frame(as_of)
    warehouse.scores = scores

    original = warehouse.insert_recommendation

    def boom(rec: dict) -> str:
        from packages.core.llm.errors import InvariantViolationError

        raise InvariantViolationError("citations")

    warehouse.insert_recommendation = boom  # type: ignore[method-assign]
    result = strategist(
        "JP",
        as_of,
        state=state,
        warehouse=warehouse,
        memory=state,
        router=None,
        scores=scores,
    )
    warehouse.insert_recommendation = original  # type: ignore[method-assign]
    assert result.status == "partial"
    assert result.metrics.get("n_discarded") == 1
    assert result.recs == []


def test_analyst_fx_skip_does_not_mark_partial() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    as_of = date(2026, 8, 21)
    state.create_job_run(job_name="collector", market="JP")
    coll_id = max(state._runs)
    state.record_job_run(coll_id, status="success")
    days = pd.bdate_range(end=as_of, periods=30)
    warehouse.prices = pd.DataFrame(
        {
            "ticker": ["7203"] * len(days),
            "market": ["JP"] * len(days),
            "trade_date": [d.date() for d in days],
            "adj_close": np.linspace(100.0, 110.0, len(days)),
            "adj_open": np.linspace(100.0, 110.0, len(days)),
            "volume": [1_000_000] * len(days),
        }
    )
    result = analyst("JP", as_of, state=state, warehouse=warehouse)
    assert result.steps["fx"].status == "skipped"
    assert result.status != "failed"
    # 為替未配線だけで Analyst 全体を partial にしない
    assert result.steps["fx"].status == "skipped"
    if result.status == "partial":
        assert "fx" not in (result.metrics.get("failed_steps") or [])


def test_collector_empty_documents_without_coverage_is_partial() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    steps = {name: _ok for name, _required in COLLECTOR_STEPS}
    steps["documents"] = lambda market, as_of: {"rows": 0, "batches": 1}
    result = collector(
        "JP",
        date(2026, 8, 28),
        state=state,
        warehouse=warehouse,
        steps=steps,
    )
    assert result.status == "partial"
    assert result.steps["documents"].status == "failed"


def test_collector_empty_documents_with_coverage_is_success() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    warehouse.coverage["documents"] = date(2026, 8, 20)
    steps = {name: _ok for name, _required in COLLECTOR_STEPS}
    steps["documents"] = lambda market, as_of: {"rows": 0, "batches": 1}
    result = collector(
        "JP",
        date(2026, 8, 28),
        state=state,
        warehouse=warehouse,
        steps=steps,
    )
    assert result.status == "success"
    assert result.steps["documents"].status == "success"


def test_pipeline_dependencies_include_router_ranker_keys(tmp_path: Path) -> None:
    class _Settings:
        gemini_api_key = ""
        openai_api_key = ""
        anthropic_api_key = ""
        llm_daily_cap_usd = 1.0
        llm_monthly_cap_usd = 20.0
        llm_kill_switch = False
        jquants_plan = "free"
        data_dir = tmp_path

    deps = pipeline_dependencies(
        FakeStateRepo(), FakeWarehouse(), market="JP", settings=_Settings()
    )
    assert set(deps) >= {"router", "ranker", "memory", "jquants_plan"}
    assert deps["router"] is None
    assert deps["ranker"] is None
    assert deps["jquants_plan"] == "free"


def test_try_load_ranker_reads_artifact(tmp_path: Path) -> None:
    ranker = FittedRanker(
        backend="ols",
        feature_names=["f1"],
        n_trials=1,
        ols_coef={"mean": np.array([0.1]), "q20": np.array([0.1]), "q80": np.array([0.1])},
        ols_intercept={"mean": 0.0, "q20": -0.02, "q80": 0.02},
    )
    path = ranker_artifact_path(tmp_path, "JP")
    save_fitted_ranker(ranker, path)
    loaded = load_fitted_ranker(path)
    assert loaded is not None
    assert loaded.backend == "ols"

    class _Settings:
        data_dir = tmp_path

    assert try_load_ranker(_Settings(), market="JP") is not None
