"""週次深掘り・月次 ranker 再学習・GARCH 再推定（docs/08-agent-loop.md §2）。"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from packages.core.factors.calendar import TradingCalendar
from packages.core.factors.labels import make_label
from packages.core.factors.pipeline import FEATURE_VERSION
from packages.core.interfaces.storage import JobRunRepo, MemoryRecord, MemoryRepo, WarehouseRepo
from packages.core.llm.errors import CostCapExceeded, KillSwitchActive
from packages.core.llm.prompts import render_prompt
from packages.core.llm.router import LLMRouter
from packages.core.llm.schemas import WeeklyReviewOutput
from packages.core.models.errors import InsufficientHistoryError
from packages.core.models.garch import compute_vol_features
from packages.core.models.ranker import ranker_artifact_path, save_fitted_ranker, train_ranker
from services.agent.deps import begin_run, finish_run
from services.agent.jobs.evaluator import update_memory
from services.agent.types import JobResult, StepResult

logger = logging.getLogger(__name__)

GARCH_MAX_TICKERS = 80
RETRAIN_N_TRIALS = 8
RETRAIN_LOOKBACK_DAYS = 400


def weekly_review(
    market: str,
    as_of: date,
    *,
    state: JobRunRepo,
    warehouse: WarehouseRepo,
    memory: MemoryRepo | None = None,
    router: LLMRouter | None = None,
    trigger: str = "schedule",
    parent_run_id: int | None = None,
) -> JobResult:
    """土曜の deep 層レビュー。キーが無ければ集計だけ残して partial。"""
    run_id = begin_run(
        state, job_name="weekly_review", market=market, trigger=trigger, parent_run_id=parent_run_id
    )
    recs = warehouse.get_recommendations(market=market, limit=80) or []
    outcomes_df = warehouse.read_recommendation_outcomes(market=market)
    outcomes = outcomes_df.to_dict(orient="records") if outcomes_df is not None and not outcomes_df.empty else []
    metrics: dict[str, Any] = {
        "n_recs": len(recs),
        "n_outcomes": len(outcomes),
    }
    if outcomes:
        hits = [bool(o.get("is_hit")) for o in outcomes]
        metrics["hit_rate"] = float(np.mean(hits))
    status = "success"
    if router is None:
        status = "partial"
        metrics["llm_skipped"] = True
    else:
        try:
            existing = memory.list_memory() if memory is not None else []
            rendered = render_prompt(
                "weekly_review.jinja",
                as_of=as_of,
                n_recs=len(recs),
                n_outcomes=len(outcomes),
                hit_rate=metrics.get("hit_rate"),
                hit_rate_by_conviction={},
                weight_proposal=None,
                recs=recs[:20],
                outcomes=outcomes[:20],
                existing_memory=existing[:15],
            )
            resp = router.complete(
                tier="deep",
                purpose="weekly_review",
                messages=[{"role": "user", "content": rendered}],
                response_schema=WeeklyReviewOutput,
                job_run_id=run_id,
                prompt_name="weekly_review.jinja",
                prompt_body=rendered,
            )
            parsed = resp.parsed
            if parsed is not None:
                metrics["summary_ja"] = parsed.summary_ja
                metrics["n_action_items"] = len(parsed.action_items_ja)
                if memory is not None and parsed.lessons:
                    existing_all = memory.list_memory(include_inactive=True)
                    upd = update_memory(list(parsed.lessons), existing_all)
                    for lesson in upd["added"]:
                        memory.insert_memory(
                            MemoryRecord(
                                memory_id=f"W{len(existing_all) + 1:04d}",
                                scope=lesson.scope,
                                category=lesson.category,
                                lesson_ja=lesson.lesson_ja,
                                evidence_ja=lesson.evidence_ja,
                                n_observations=lesson.n_observations,
                                confidence=lesson.confidence,
                                scope_value=lesson.scope_value,
                            )
                        )
                    metrics["memory_added"] = len(upd["added"])
        except (CostCapExceeded, KillSwitchActive):
            status = "partial"
            metrics["llm_capped"] = True
        except Exception as exc:
            status = "partial"
            metrics["error"] = type(exc).__name__
    finish_run(state, run_id, status=status, metrics=metrics)
    return JobResult(
        job_name="weekly_review",
        status=status,
        market=market,
        as_of=as_of,
        run_id=run_id,
        steps={"review": StepResult(status=status)},
        metrics=metrics,
    )


def model_retrain(
    market: str,
    as_of: date,
    *,
    state: JobRunRepo,
    warehouse: WarehouseRepo,
    data_dir: Any | None = None,
    n_trials: int = RETRAIN_N_TRIALS,
    trigger: str = "schedule",
    parent_run_id: int | None = None,
) -> JobResult:
    """月次 ranker 再学習。サンプル不足なら partial で成果物は残さない。"""
    run_id = begin_run(
        state, job_name="model_retrain", market=market, trigger=trigger, parent_run_id=parent_run_id
    )
    metrics: dict[str, Any] = {"n_trials": n_trials}
    status = "success"
    try:
        start = as_of - timedelta(days=RETRAIN_LOOKBACK_DAYS)
        features = warehouse.read_features_daily(market=market, start=start, end=as_of)
        prices = warehouse.read_prices_daily(market=market, start=start, end=as_of)
        if features is None or getattr(features, "empty", True):
            raise InsufficientHistoryError("特徴量が空です")
        work, labels = _panel_for_ranker(features, prices, as_of)
        ranker = train_ranker(
            work,
            labels,
            n_trials=n_trials,
            warehouse=warehouse,
            model_kind="ranker_h20",
        )
        if data_dir is not None:
            path = save_fitted_ranker(ranker, ranker_artifact_path(data_dir, market))
            metrics["artifact"] = str(path)
        metrics["backend"] = ranker.backend
        metrics["n_rows"] = ranker.metrics.get("n_rows")
    except InsufficientHistoryError as exc:
        status = "partial"
        metrics["error"] = str(exc)
    except Exception as exc:
        status = "failed"
        metrics["error"] = f"{type(exc).__name__}: {exc}"
        logger.exception("model_retrain が失敗しました")
    finish_run(state, run_id, status=status, metrics=metrics)
    return JobResult(
        job_name="model_retrain",
        status=status,
        market=market,
        as_of=as_of,
        run_id=run_id,
        steps={"train": StepResult(status=status)},
        metrics=metrics,
    )


def garch_refit(
    market: str,
    as_of: date,
    *,
    state: JobRunRepo,
    warehouse: WarehouseRepo,
    trigger: str = "schedule",
    parent_run_id: int | None = None,
    max_tickers: int = GARCH_MAX_TICKERS,
) -> JobResult:
    """週次 GARCH 再推定。失敗した銘柄は実現ボラへフォールバックし partial。"""
    run_id = begin_run(
        state, job_name="garch_refit", market=market, trigger=trigger, parent_run_id=parent_run_id
    )
    start = as_of - timedelta(days=800)
    features = warehouse.read_features_daily(market=market, as_of=as_of)
    tickers: list[str] = []
    if features is not None and not getattr(features, "empty", True) and "ticker" in features.columns:
        tickers = sorted({str(t) for t in features["ticker"].tolist()})[:max_tickers]
    if not tickers:
        prices_all = warehouse.read_prices_daily(market=market, start=as_of - timedelta(days=5), end=as_of)
        if prices_all is not None and not prices_all.empty and "ticker" in prices_all.columns:
            tickers = sorted({str(t) for t in prices_all["ticker"].tolist()})[:max_tickers]
    n_ok = 0
    n_fallback = 0
    rows: list[dict[str, Any]] = []
    for ticker in tickers:
        px = warehouse.read_prices_daily(tickers=[ticker], start=start, end=as_of)
        log_ret = _log_returns(px, ticker)
        realized_60 = _realized_vol(log_ret, 60)
        realized_20 = _realized_vol(log_ret, 20)
        result = compute_vol_features(
            log_ret,
            realized_vol_20d=realized_20,
            realized_vol_60d=realized_60,
            entity=ticker,
            as_of=as_of,
            quality_sink=warehouse,
        )
        if result.get("garch_vol_20d") is None:
            n_fallback += 1
        else:
            n_ok += 1
        rows.append(
            {
                "ticker": ticker,
                "market": market,
                "as_of": as_of,
                "feature_version": FEATURE_VERSION,
                "currency": "JPY" if market == "JP" else "USD",
                "garch_vol_1d": result.get("garch_vol_1d"),
                "garch_vol_20d": result.get("garch_vol_20d"),
                "realized_vol_20d": realized_20,
                "realized_vol_60d": realized_60,
            }
        )
    if rows:
        warehouse.upsert_features_daily(rows)
    metrics = {"n_tickers": len(tickers), "n_fitted": n_ok, "n_fallback": n_fallback}
    status = "success" if n_fallback == 0 and tickers else "partial"
    if not tickers:
        metrics["error"] = "対象銘柄がありません"
    finish_run(state, run_id, status=status, metrics=metrics)
    return JobResult(
        job_name="garch_refit",
        status=status,
        market=market,
        as_of=as_of,
        run_id=run_id,
        steps={"garch": StepResult(status=status)},
        metrics=metrics,
    )


def _panel_for_ranker(
    features: pd.DataFrame, prices: pd.DataFrame, as_of: date
) -> tuple[pd.DataFrame, pd.Series]:
    work = features.copy()
    if "as_of" not in work.columns or "ticker" not in work.columns:
        raise InsufficientHistoryError("features に as_of / ticker がありません")
    work["as_of"] = pd.to_datetime(work["as_of"], errors="coerce").dt.date
    dates = sorted({d for d in work["as_of"].tolist() if d is not None and d < as_of})
    dates = dates[-80:]
    cal = TradingCalendar.from_prices(prices) if not prices.empty else TradingCalendar()
    parts: list[pd.DataFrame] = []
    labels: list[pd.Series] = []
    for day in dates:
        label = make_label(prices, day, 20, calendar=cal)
        if label.empty or label.notna().sum() == 0:
            continue
        slice_ = work.loc[work["as_of"] == day].copy()
        if slice_.empty:
            continue
        slice_ = slice_.assign(_y=slice_["ticker"].astype(str).map(label))
        parts.append(slice_)
        labels.append(slice_["_y"])
    if not parts:
        raise InsufficientHistoryError("ラベルを付けられる日付がありません")
    panel = pd.concat(parts, ignore_index=True)
    y = pd.concat(labels, ignore_index=True)
    y.name = "fwd_ret_20d"
    return panel, y


def _log_returns(prices: pd.DataFrame, ticker: str) -> pd.Series:
    if prices is None or prices.empty:
        return pd.Series(dtype=float)
    work = prices.copy()
    if "ticker" in work.columns:
        work = work.loc[work["ticker"].astype(str) == ticker]
    col = "adj_close" if "adj_close" in work.columns else "close"
    if col not in work.columns or "trade_date" not in work.columns:
        return pd.Series(dtype=float)
    work = work.sort_values("trade_date")
    series = pd.to_numeric(work[col], errors="coerce")
    return np.log(series.where(series > 0)).diff().dropna()


def _realized_vol(log_ret: pd.Series, window: int) -> float | None:
    if log_ret is None or len(log_ret) < window:
        return None
    daily = float(log_ret.tail(window).std())
    if daily != daily:
        return None
    return daily * float(np.sqrt(252))
