"""Analyst: 特徴量・GARCH・為替・ML予測・スコア（docs/08-agent-loop.md §4）。

LLM は使わない。部分失敗は機能縮退。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
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
# ボラ推定に最低限必要な営業日。これ未満は予測せず skip（ジョブは落とさない）。
MIN_FX_SPOT_POINTS = 20
# docs/04-analysis-engine.md §2.3 / FRED series（02-data-ingestion.md §8.2）
FX_US_10Y = "DGS10"
FX_US_2Y = "DGS2"
FX_JP_10Y = "IRLTLT01JPM156N"
FX_US_CPI = "CPIAUCSL"
FX_JP_CPI = "CPALTT01JPM659N"
_MACRO_DATE_COLS = ("observation_date", "trade_date", "date")


def _load_macro_rows(
    warehouse: WarehouseRepo, series_id: str, as_of: date
) -> list[Any]:
    getter = getattr(warehouse, "get_macro_as_of", None)
    if callable(getter):
        try:
            return list(getter(series_id, as_of=as_of, limit=FX_LOOKBACK_OBS) or [])
        except TypeError:
            return list(
                getter(series_id=series_id, as_of=as_of, limit=FX_LOOKBACK_OBS) or []
            )
        except Exception:
            return []
    reader = getattr(warehouse, "read_macro_as_of", None)
    if not callable(reader):
        return []
    try:
        frame = reader(series_ids=[series_id], as_of=as_of)
    except Exception:
        return []
    if frame is None or getattr(frame, "empty", True):
        return []
    return frame.to_dict(orient="records")


def _rows_to_series(rows: list[Any]) -> pd.Series | None:
    if not rows:
        return None
    frame = pd.DataFrame(rows)
    date_col = next((c for c in _MACRO_DATE_COLS if c in frame.columns), None)
    if date_col is None or "value" not in frame.columns:
        return None
    series = pd.Series(
        pd.to_numeric(frame["value"], errors="coerce").to_numpy(),
        index=pd.to_datetime(frame[date_col]),
    )
    series = series.dropna().sort_index()
    series = series[~series.index.duplicated(keep="last")]
    return None if series.empty else series


def _load_fx_spot(warehouse: WarehouseRepo, as_of: date) -> pd.DataFrame | None:
    """macro_series の DEXJPUS を Analyst の入力形式に揃える。"""
    rows = _load_macro_rows(warehouse, FX_SERIES_ID, as_of)
    if not rows:
        return None
    return pd.DataFrame(rows)


def _build_fx_exog(
    warehouse: WarehouseRepo, as_of: date, index: pd.DatetimeIndex
) -> pd.DataFrame | None:
    """金利差外生変数。マクロは vintage_date <= as_of（get_macro_as_of）。

    日本 2年金利の FRED id はカタログに無いので `rate_diff_2y` は米 2年のみ。
    `rate_diff_10y` が作れなければ ARIMAX に渡さない（RW のみ）。
    """
    us10 = _rows_to_series(_load_macro_rows(warehouse, FX_US_10Y, as_of))
    if us10 is None:
        return None
    us10_a = us10.reindex(index).ffill()
    if us10_a.isna().all():
        return None
    jp10 = _rows_to_series(_load_macro_rows(warehouse, FX_JP_10Y, as_of))
    jp10_a = jp10.reindex(index).ffill() if jp10 is not None else None
    if jp10_a is not None and not jp10_a.isna().all():
        rate_10 = us10_a - jp10_a
    else:
        rate_10 = us10_a
    exog = pd.DataFrame({"rate_diff_10y": rate_10}, index=index)
    us2 = _rows_to_series(_load_macro_rows(warehouse, FX_US_2Y, as_of))
    if us2 is not None:
        us2_a = us2.reindex(index).ffill()
        if not us2_a.isna().all():
            exog["rate_diff_2y"] = us2_a
    # 初日の差分は未定義。未来方向の bfill はしない。
    exog["d_rate_diff_10y"] = exog["rate_diff_10y"].diff().fillna(0.0)
    us_cpi = _rows_to_series(_load_macro_rows(warehouse, FX_US_CPI, as_of))
    jp_cpi = _rows_to_series(_load_macro_rows(warehouse, FX_JP_CPI, as_of))
    if us_cpi is not None and jp_cpi is not None and jp10_a is not None:
        us_cpi_a = us_cpi.reindex(index).ffill()
        jp_cpi_a = jp_cpi.reindex(index).ffill()
        us_yoy = us_cpi_a.pct_change(periods=252) * 100.0
        jp_yoy = jp_cpi_a.pct_change(periods=252) * 100.0
        real = (us10_a - us_yoy) - (jp10_a - jp_yoy)
        if real.notna().sum() >= MIN_FX_SPOT_POINTS:
            exog["real_rate_diff"] = real
    exog = exog.replace([np.inf, -np.inf], np.nan)
    if exog["rate_diff_10y"].notna().sum() < MIN_FX_SPOT_POINTS:
        return None
    return exog


def _spot_series_from_fx(fx: pd.DataFrame) -> pd.Series | None:
    value_col = "value" if "value" in fx.columns else None
    if value_col is None:
        return None
    date_col = next((c for c in _MACRO_DATE_COLS if c in fx.columns), None)
    if date_col is None:
        return None
    spot = pd.Series(
        pd.to_numeric(fx[value_col], errors="coerce").to_numpy(),
        index=pd.to_datetime(fx[date_col]),
    )
    spot = spot.dropna().sort_index()
    spot = spot[~spot.index.duplicated(keep="last")]
    return None if spot.empty else spot


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
    run_id: int | None = None,
) -> JobResult:
    run_id = begin_run(
        state,
        job_name="analyst",
        market=market,
        trigger=trigger,
        parent_run_id=parent_run_id,
        run_id=run_id,
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
            spot = _spot_series_from_fx(fx)
            if spot is None:
                steps["fx"] = StepResult(status="skipped", metrics={"reason": "spot_missing"})
            elif int(spot.size) < MIN_FX_SPOT_POINTS:
                steps["fx"] = StepResult(
                    status="skipped",
                    metrics={"reason": "too_short", "n": int(spot.size)},
                )
            else:
                exog = (
                    _build_fx_exog(warehouse, as_of, spot.index)
                    if int(spot.size) >= 60
                    else None
                )
                bundle = forecast_fx(as_of=as_of, spot=spot, exog=exog, horizon=5)
                warehouse.upsert_fx_forecasts(pd.DataFrame(bundle.as_rows()))
                dm = bundle.dm
                steps["fx"] = StepResult(
                    status="success",
                    metrics={
                        "n": int(spot.size),
                        "n_models": len(bundle.as_rows()),
                        "n_validation": bundle.n_validation,
                        "beats_baseline": bool(dm.beats_baseline) if dm is not None else False,
                    },
                )
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
