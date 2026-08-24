"""Analyst: 特徴量・GARCH・為替・ML予測・スコア（docs/08-agent-loop.md §4）。

LLM は使わない。部分失敗は機能縮退。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from packages.core.factors.pipeline import compute_features
from packages.core.factors.scoring import score_cross_section
from packages.core.interfaces.storage import JobRunRepo, WarehouseRepo
from packages.core.models.arimax import forecast_fx
from packages.core.models.garch import compute_vol_features
from packages.core.models.ranker import FittedRanker
from services.agent.deps import UpstreamFailed, begin_run, finish_run, require_not_failed
from services.agent.types import JobResult, StepResult


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
            prices = warehouse.read_prices_daily(market=market, end=as_of)
        if securities is None:
            try:
                securities = warehouse.read_securities(market=market, as_of=as_of)
            except Exception:
                securities = None
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
        if not features.empty:
            warehouse.upsert_features_daily(features)
        steps["features"] = StepResult(
            status="success", metrics={"n": int(len(features))}
        )
        metrics["n_features"] = int(len(features))
    except Exception as exc:
        overall = "partial"
        features = pd.DataFrame()
        steps["features"] = StepResult(status="failed", error=str(exc))

    # --- GARCH（銘柄ごと。失敗は実現ボラへ） ---
    garch_fallback = 0
    if not features.empty and prices is not None and "adj_close" in prices.columns:
        try:
            work = prices.copy()
            work["trade_date"] = pd.to_datetime(work["trade_date"]).dt.date
            for ticker, g in work.groupby("ticker"):
                g = g.sort_values("trade_date")
                close = pd.to_numeric(g["adj_close"], errors="coerce")
                log_ret = np.log(close.where(close > 0)).diff().dropna()
                rv20 = features.loc[features["ticker"] == str(ticker), "realized_vol_20d"]
                rv60 = features.loc[features["ticker"] == str(ticker), "realized_vol_60d"]
                result = compute_vol_features(
                    log_ret,
                    realized_vol_20d=float(rv20.iloc[0]) if len(rv20) else None,
                    realized_vol_60d=float(rv60.iloc[0]) if len(rv60) else None,
                    quality_sink=warehouse,
                    entity=str(ticker),
                    as_of=as_of,
                )
                if "GARCH_FALLBACK" in result["quality_flags"]:
                    garch_fallback += 1
            steps["garch"] = StepResult(
                status="success", metrics={"fallback": garch_fallback}
            )
        except Exception as exc:
            overall = "partial"
            steps["garch"] = StepResult(status="failed", error=str(exc))
    metrics["garch_fallback"] = garch_fallback

    # --- 為替 ---
    try:
        if fx is not None and not fx.empty and "value" in fx.columns:
            spot = pd.Series(
                pd.to_numeric(fx["value"], errors="coerce").to_numpy(),
                index=pd.to_datetime(fx.get("observation_date", fx.get("trade_date"))),
            )
            bundle = forecast_fx(as_of=as_of, spot=spot, exog=None, horizon=5)
            warehouse.upsert_fx_forecasts(pd.DataFrame(bundle.as_rows()))
            steps["fx"] = StepResult(status="success")
        else:
            steps["fx"] = StepResult(status="skipped", error="外生変数/スポット欠損")
            if overall == "success":
                overall = "partial"
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

    finish_run(state, run_id, status=overall, metrics=metrics)
    return JobResult(
        job_name="analyst",
        status=overall,
        market=market,
        as_of=as_of,
        run_id=run_id,
        steps=steps,
        metrics=metrics,
    )
