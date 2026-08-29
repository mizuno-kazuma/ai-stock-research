"""Analyst: 特徴量・GARCH・為替・ML予測・スコア（docs/08-agent-loop.md §4）。

LLM は使わない。部分失敗は機能縮退。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from packages.core.factors.pipeline import compute_features
from packages.core.factors.scoring import score_cross_section
from packages.core.interfaces.storage import JobRunRepo, WarehouseRepo
from packages.core.models.arimax import forecast_fx
from packages.core.models.ranker import FittedRanker
from services.agent.deps import (
    UpstreamFailed,
    attach_step_failures,
    begin_run,
    finish_run,
    first_step_error,
    require_not_failed,
)
from services.agent.types import JobResult, StepResult

# mom_12_1 / ret_252 に必要な約 252 営業日 + 余裕。全履歴を pandas に載せない。
FEATURE_LOOKBACK_CALENDAR_DAYS = 420
FX_SERIES_ID = "DEXJPUS"
FX_LOOKBACK_OBS = 400


def _load_fx_spot(warehouse: WarehouseRepo, as_of: date) -> pd.DataFrame | None:
    """macro_series の DEXJPUS を Analyst の入力形式に揃える。"""
    getter = getattr(warehouse, "get_macro_as_of", None)
    rows: list[Any]
    if callable(getter):
        try:
            rows = list(getter(FX_SERIES_ID, as_of=as_of, limit=FX_LOOKBACK_OBS) or [])
        except TypeError:
            rows = list(getter(series_id=FX_SERIES_ID, as_of=as_of, limit=FX_LOOKBACK_OBS) or [])
        except Exception:
            rows = []
    else:
        reader = getattr(warehouse, "read_macro_as_of", None)
        if not callable(reader):
            return None
        try:
            frame = reader(series_ids=[FX_SERIES_ID], as_of=as_of)
        except Exception:
            return None
        if frame is None or getattr(frame, "empty", True):
            return None
        return frame
    if not rows:
        return None
    return pd.DataFrame(rows)


def analyst(
    market: str,
    as_of: date,
    *,
    state: JobRunRepo,
    warehouse: WarehouseRepo,
    ranker: FittedRanker | None = None,
    prices: pd.DataFrame | None = None,
    securities: pd.DataFrame | None = None,
    financials: pd.DataFrame | None = None,
    fx: pd.DataFrame | None = None,
    trigger: str = "schedule",
    parent_run_id: int | None = None,
) -> JobResult:
    run_id = begin_run(
        state, job_name="analyst", market=market, trigger=trigger, parent_run_id=parent_run_id
    )
    steps: dict[str, StepResult] = {}
    try:
        require_not_failed(
            state, job_name="collector", market=market, on_date=as_of, required=True
        )
    except UpstreamFailed as exc:
        finish_run(state, run_id, status="failed", error=exc)
        return JobResult(
            job_name="analyst",
            status="failed",
            market=market,
            as_of=as_of,
            run_id=run_id,
            error=str(exc),
        )

    overall = "success"
    metrics: dict[str, Any] = {}

    # --- 特徴量 ---
    try:
        if prices is None:
            start = as_of - timedelta(days=FEATURE_LOOKBACK_CALENDAR_DAYS)
            prices = warehouse.read_prices_daily(market=market, start=start, end=as_of)
        if securities is None:
            try:
                securities = warehouse.read_securities(market=market, as_of=as_of)
            except Exception:
                securities = None
        if fx is None:
            fx = _load_fx_spot(warehouse, as_of)
        from packages.core.factors.pipeline import build_pit_context

        ctx = build_pit_context(
            as_of=as_of,
            market=market,
            prices=prices,
            securities=securities,
            financials=financials,
            fx=fx,
        )
        features = compute_features(ctx)
        n_features = int(len(features))
        metrics["n_features"] = n_features
        if not features.empty:
            try:
                warehouse.upsert_features_daily(features)
                steps["features"] = StepResult(
                    status="success", metrics={"n": n_features}
                )
            except Exception as exc:
                overall = "partial"
                steps["features"] = StepResult(
                    status="failed",
                    error=f"保存に失敗: {exc}",
                    metrics={"n": n_features},
                )
        else:
            steps["features"] = StepResult(
                status="success", metrics={"n": 0}
            )
    except Exception as exc:
        overall = "partial"
        features = pd.DataFrame()
        steps["features"] = StepResult(status="failed", error=str(exc))

    # --- GARCH（日次では全銘柄推定しない。週次 refit_garch が担当） ---
    # docs/04-analysis-engine.md §1.3.1: 全銘柄は実現ボラ。日次の銘柄ループは
    # 結果を features に書き戻しておらず、数千銘柄で数時間かかる。
    steps["garch"] = StepResult(status="skipped", metrics={"reason": "weekly_refit"})
    metrics["garch_fallback"] = 0

    # --- 為替 ---
    try:
        if fx is None or getattr(fx, "empty", True):
            steps["fx"] = StepResult(status="skipped", metrics={"reason": "spot_missing"})
        else:
            value_col = "value" if "value" in fx.columns else None
            if value_col is None:
                steps["fx"] = StepResult(status="skipped", metrics={"reason": "spot_missing"})
            else:
                date_col = (
                    "observation_date"
                    if "observation_date" in fx.columns
                    else "trade_date"
                )
                spot = pd.Series(
                    pd.to_numeric(fx[value_col], errors="coerce").to_numpy(),
                    index=pd.to_datetime(fx[date_col]),
                )
                bundle = forecast_fx(as_of=as_of, spot=spot, exog=None, horizon=5)
                warehouse.upsert_fx_forecasts(pd.DataFrame(bundle.as_rows()))
                steps["fx"] = StepResult(status="success")
    except Exception as exc:
        overall = "partial"
        steps["fx"] = StepResult(status="failed", error=str(exc))

    # --- ML 予測 ---
    ml = None
    if ranker is None:
        steps["ml"] = StepResult(status="skipped", error="モデル未学習")
        metrics["ml_untrained"] = True
    elif features.empty:
        steps["ml"] = StepResult(status="skipped", error="特徴量なし")
    else:
        try:
            pred = ranker.predict(features)
            ml = pred.rename(
                columns={
                    "ml_pred": "ml_pred_h20",
                    "ml_pred_lo": "ml_pred_h20_lo",
                    "ml_pred_hi": "ml_pred_h20_hi",
                }
            )
            if "ticker" in ml.columns:
                ml = ml.set_index("ticker")
            steps["ml"] = StepResult(status="success")
        except Exception as exc:
            overall = "partial"
            steps["ml"] = StepResult(status="failed", error=str(exc))

    # --- スコア ---
    try:
        if features.empty:
            raise RuntimeError("特徴量が空")
        scores = score_cross_section(
            features, market=market, horizon="H20", ml_predictions=ml
        )
        warehouse.upsert_scores_daily(scores)
        steps["scores"] = StepResult(status="success", metrics={"n": int(len(scores))})
        metrics["n_scores"] = int(len(scores))
        if "quant_score" in scores.columns:
            metrics["quant_mean"] = float(pd.to_numeric(scores["quant_score"], errors="coerce").mean())
    except Exception as exc:
        overall = "failed" if features.empty else "partial"
        steps["scores"] = StepResult(status="failed", error=str(exc))

    metrics = attach_step_failures(metrics, steps)
    job_error = first_step_error(steps) if overall in {"failed", "partial"} else None
    finish_run(
        state,
        run_id,
        status=overall,
        metrics=metrics,
        error=RuntimeError(job_error) if job_error else None,
    )
    return JobResult(
        job_name="analyst",
        status=overall,
        market=market,
        as_of=as_of,
        run_id=run_id,
        steps=steps,
        metrics=metrics,
        error=job_error,
    )
