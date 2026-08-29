"""モデルラボ（docs/09-api-spec.md §2.7）。"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status

from packages.schemas.common import Envelope, OkResponse
from packages.schemas.model_lab import (
    BacktestList,
    BacktestRequest,
    BacktestRun,
    BacktestTradeList,
    EquityCurve,
    FactorWeightSet,
    FactorWeightsResponse,
    FeatureImportance,
    FeatureImportanceResponse,
    IcPoint,
    IcTimeseries,
    JobAccepted,
    ModelHealth,
    ModelRun,
    ModelRunList,
    Quintile,
    ValidationSpec,
)
from services.api.deps import AppState, User, get_app_state, require_user
from services.api.envelope import wrap
from services.api.errors import not_found
from services.api.runtime import (
    execute_backtest,
    load_backtest_from_jobs,
    load_backtest_trades,
    load_equity_points,
    queue_backtest_row,
    resolve_n_trials,
)
from services.api.util import as_date, as_dict, as_list, as_utc, resolve_market

router = APIRouter(tags=["models"])


def _model_from_seed(row: dict) -> ModelRun:
    return ModelRun(
        run_id=row["run_id"],
        model_kind=row.get("kind") or row.get("model_kind") or "ranker",
        model_version=row.get("feature_version") or "v3",
        market=row.get("market"),
        horizon=row.get("horizon"),
        train_start=as_date(row.get("period_start")),
        train_end=as_date(row.get("period_end")),
        cv_scheme="purged_walk_forward",
        purge_days=20,
        embargo_days=5,
        n_folds=len(row.get("fold_rank_ic") or []) or 8,
        feature_version=row.get("feature_version") or "v3",
        feature_list=[],
        n_trials=row.get("n_trials"),
        fold_rank_ic=list(row.get("fold_rank_ic") or []),
        fold_ic_std=row.get("fold_ic_std"),
        started_at=as_utc(row.get("trained_at")),
        status="success" if row.get("status") in {None, "active"} else str(row.get("status")),
    )


def _model_from_row(row: dict) -> ModelRun:
    return ModelRun(
        run_id=row["run_id"],
        model_kind=row["model_kind"],
        model_version=row.get("model_version"),
        market=row.get("market"),
        horizon=row.get("horizon"),
        train_start=as_date(row.get("train_start")),
        train_end=as_date(row.get("train_end")),
        valid_start=as_date(row.get("valid_start")),
        valid_end=as_date(row.get("valid_end")),
        cv_scheme=row.get("cv_scheme") or "purged_walk_forward",
        purge_days=row.get("purge_days"),
        embargo_days=row.get("embargo_days"),
        n_folds=row.get("n_folds"),
        feature_version=row.get("feature_version"),
        feature_list=as_list(row.get("feature_list")),
        hyperparams=as_dict(row.get("hyperparams")) or None,
        input_snapshot_hash=row.get("input_snapshot_hash"),
        metrics=as_dict(row.get("metrics")) or None,
        n_trials=row.get("n_trials"),
        fold_rank_ic=list(row.get("fold_rank_ic") or []),
        fold_ic_std=row.get("fold_ic_std"),
        artifact_path=row.get("artifact_path"),
        git_commit=row.get("git_commit"),
        started_at=as_utc(row.get("started_at")),
        finished_at=as_utc(row.get("finished_at")),
        status=row.get("status") or "success",
    )


def _bt_from_any(row: dict) -> BacktestRun:
    return BacktestRun(
        backtest_id=row["backtest_id"],
        strategy_name=row.get("strategy_name") or "",
        market=row.get("market") or "JP",
        status=row.get("status") or "finished",
        model_run_id=row.get("model_run_id"),
        period_start=as_date(row.get("period_start")) or as_date("2024-08-01"),
        period_end=as_date(row.get("period_end")) or as_date("2026-08-01"),
        rebalance_freq=row.get("rebalance_freq") or "monthly",
        n_positions=int(row.get("n_positions") or 20),
        fee_bps=float(row.get("fee_bps") or 0.0),
        slippage_bps=float(row.get("slippage_bps") or 0.0),
        max_turnover_pct=float(row.get("max_turnover_pct") or 30.0),
        total_return=row.get("total_return"),
        cagr=row.get("cagr") or row.get("annualized_return"),
        annualized_return=row.get("annualized_return"),
        benchmark_annualized=row.get("benchmark_annualized"),
        excess_return=row.get("excess_return"),
        volatility=row.get("volatility"),
        sharpe=row.get("sharpe"),
        sortino=row.get("sortino"),
        max_drawdown=row.get("max_drawdown"),
        max_drawdown_period_ja=row.get("max_drawdown_period_ja"),
        calmar=row.get("calmar"),
        hit_rate=row.get("hit_rate"),
        monthly_hit_rate=row.get("monthly_hit_rate"),
        n_months=row.get("n_months"),
        profit_factor=row.get("profit_factor"),
        avg_turnover=row.get("avg_turnover"),
        realized_turnover_pct=row.get("realized_turnover_pct"),
        total_cost_bps=row.get("total_cost_bps"),
        cost_drag_annual=row.get("cost_drag_annual"),
        gross_annualized_return=row.get("gross_annualized_return"),
        n_trials=row.get("n_trials"),
        deflated_sharpe=row.get("deflated_sharpe"),
        dsr_pvalue=row.get("dsr_pvalue") or row.get("dsr_p_value"),
        is_significant=(row.get("dsr_pvalue") or row.get("dsr_p_value") or 1) < 0.05
        if (row.get("dsr_pvalue") or row.get("dsr_p_value")) is not None
        else None,
        significance_ja=row.get("significance_ja"),
        progress_pct=row.get("progress_pct"),
        elapsed_sec=row.get("elapsed_sec"),
        eta_sec=row.get("eta_sec"),
        error_ja=row.get("error_ja"),
        run_at=as_utc(row.get("run_at")),
        skew=row.get("skew"),
        kurtosis=row.get("kurtosis"),
    )


def _weight_set(row: dict, *, is_active: bool = False) -> FactorWeightSet:
    weights = as_dict(row.get("weights"))
    if "lowvol" not in weights and "volatility" in weights:
        weights["lowvol"] = weights.get("volatility")
    return FactorWeightSet(
        weight_set_id=row["weight_set_id"],
        market=row.get("market") or "JP",
        horizon=row.get("horizon") or "H20",
        weights={k: float(v) for k, v in weights.items() if isinstance(v, (int, float))},
        fitted_from=as_date(row.get("fitted_from")),
        fitted_to=as_date(row.get("fitted_to")),
        fit_method=row.get("fit_method"),
        ic_in_sample=row.get("ic_in_sample"),
        ic_out_of_sample=row.get("ic_out_of_sample"),
        n_samples=row.get("n_samples"),
        blend_ratio=row.get("blend_ratio"),
        period_ja=row.get("period_ja"),
        is_active=is_active or bool(row.get("is_active")),
        status=row.get("status"),
        activated_at=as_utc(row.get("activated_at")) or as_date(row.get("activated_at")),
        created_by=row.get("created_by"),
        created_at=as_utc(row.get("created_at")) or as_date(row.get("created_at")),
        proposed_at=as_utc(row.get("proposed_at")),
    )


@router.get("/models/runs", response_model=Envelope[ModelRunList])
def list_model_runs(
    kind: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[ModelRunList]:
    rows = state.duck.get_model_runs(model_kind=kind, limit=limit)
    items = [_model_from_row(r) for r in rows]
    if not items:
        items = [
            _model_from_seed(r)
            for r in state.payload.get("model_runs") or []
            if kind is None or r.get("kind") == kind or r.get("model_kind") == kind
        ][:limit]
    return wrap(state, ModelRunList(items=items, total=len(items)))


@router.get("/models/runs/{run_id}", response_model=Envelope[ModelRun])
def get_model_run(
    run_id: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[ModelRun]:
    row = state.duck.get_model_run(run_id)
    if row:
        return wrap(state, _model_from_row(row))
    for item in state.payload.get("model_runs") or []:
        if item.get("run_id") == run_id:
            return wrap(state, _model_from_seed(item))
    raise not_found(f"モデルラン {run_id} は存在しません。")


@router.get("/models/runs/{run_id}/feature-importance", response_model=Envelope[FeatureImportanceResponse])
def get_feature_importance(
    run_id: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[FeatureImportanceResponse]:
    health = state.payload.get("model_health") or {}
    items = [FeatureImportance.model_validate(r) for r in health.get("feature_importance") or []]
    if state.duck.get_model_run(run_id) is None and not any(
        r.get("run_id") == run_id for r in state.payload.get("model_runs") or []
    ):
        raise not_found(f"モデルラン {run_id} は存在しません。")
    return wrap(state, FeatureImportanceResponse(run_id=run_id, items=items))


@router.get("/models/runs/{run_id}/ic-timeseries", response_model=Envelope[IcTimeseries])
def get_ic_timeseries(
    run_id: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[IcTimeseries]:
    seed = next((r for r in state.payload.get("model_runs") or [] if r.get("run_id") == run_id), None)
    row = state.duck.get_model_run(run_id)
    if row is None and seed is None:
        raise not_found(f"モデルラン {run_id} は存在しません。")
    folds = list((seed or {}).get("fold_rank_ic") or (row or {}).get("fold_rank_ic") or [])
    points = [
        IcPoint(as_of=as_date("2026-08-01"), rank_ic=float(v))  # placeholder dates
        for v in folds
    ]
    mean = sum(folds) / len(folds) if folds else None
    return wrap(state, IcTimeseries(run_id=run_id, points=points, mean_ic=mean))


@router.get("/models/health", response_model=Envelope[ModelHealth])
def get_model_health(
    market: str = Query(default="JP"),
    horizon: str = Query(default="H20"),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[ModelHealth]:
    market = resolve_market(market)
    raw = state.payload.get("model_health") or {}
    if raw:
        val = raw.get("validation") or {}
        return wrap(
            state,
            ModelHealth(
                market=raw.get("market") or market,
                horizon=raw.get("horizon") or horizon,
                as_of=as_date(raw.get("as_of")),
                rank_ic_20d=raw.get("rank_ic_20d"),
                rank_ic_20d_n=raw.get("rank_ic_20d_n"),
                rank_ic_3m=raw.get("rank_ic_3m"),
                rank_ic_3m_n=raw.get("rank_ic_3m_n"),
                rank_ic_3m_tstat=raw.get("rank_ic_3m_tstat"),
                coverage_pct=raw.get("coverage_pct"),
                covered_tickers=raw.get("covered_tickers"),
                universe_tickers=raw.get("universe_tickers"),
                degradation_detected=bool(raw.get("degradation_detected")),
                ic_mean_period=raw.get("ic_mean_period"),
                ic_std_period=raw.get("ic_std_period"),
                ic_positive_days_pct=raw.get("ic_positive_days_pct"),
                ic_n_days=raw.get("ic_n_days"),
                quintiles=[Quintile.model_validate(q) for q in raw.get("quintiles") or []],
                quintile_spread=raw.get("quintile_spread"),
                monotonic=raw.get("monotonic"),
                feature_importance=[
                    FeatureImportance.model_validate(f) for f in raw.get("feature_importance") or []
                ],
                validation=ValidationSpec.model_validate(val) if val else None,
                status="normal" if not raw.get("degradation_detected") else "degraded",
            ),
        )
    return wrap(
        state,
        ModelHealth(market=market, horizon=horizon, status="unknown"),  # type: ignore[arg-type]
    )


@router.get("/backtests", response_model=Envelope[BacktestList])
def list_backtests(
    limit: int = Query(default=20, ge=1, le=100),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[BacktestList]:
    rows = state.duck.get_backtest_runs(limit=limit)
    items = [_bt_from_any(r) for r in rows]
    if not items:
        items = [_bt_from_any(r) for r in state.payload.get("backtests") or []][:limit]
    return wrap(state, BacktestList(items=items, total=len(items)))


@router.get("/backtests/{backtest_id}", response_model=Envelope[BacktestRun])
def get_backtest(
    backtest_id: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[BacktestRun]:
    row = state.duck.get_backtest_run(backtest_id)
    if row:
        return wrap(state, _bt_from_any(row))
    for item in state.payload.get("backtests") or []:
        if item.get("backtest_id") == backtest_id:
            return wrap(state, _bt_from_any(item))
    from_job = load_backtest_from_jobs(state, backtest_id)
    if from_job:
        return wrap(state, _bt_from_any(from_job))
    raise not_found(f"バックテスト {backtest_id} は存在しません。")


@router.get("/backtests/{backtest_id}/equity-curve", response_model=Envelope[EquityCurve])
def get_equity_curve(
    backtest_id: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[EquityCurve]:
    get_backtest(backtest_id, _user, state)
    return wrap(state, EquityCurve(backtest_id=backtest_id, points=load_equity_points(state, backtest_id)))


@router.get("/backtests/{backtest_id}/trades", response_model=Envelope[BacktestTradeList])
def get_backtest_trades(
    backtest_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[BacktestTradeList]:
    get_backtest(backtest_id, _user, state)
    items = load_backtest_trades(state, backtest_id, limit=limit)
    return wrap(state, BacktestTradeList(backtest_id=backtest_id, items=items, total=len(items)))


@router.post("/backtests", response_model=Envelope[JobAccepted], status_code=status.HTTP_202_ACCEPTED)
def create_backtest(
    body: BacktestRequest,
    background: BackgroundTasks,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[JobAccepted]:
    run_id = state.sqlite.start_job_run("backtest", trigger="manual", market=body.market)
    backtest_id = f"bt_queued_{run_id}"
    n_trials = resolve_n_trials(state, body)
    state.sqlite.update_job_run(
        run_id,
        status="running",
        metrics={
            "backtest_id": backtest_id,
            "strategy_name": body.strategy_name,
            "market": body.market,
            "period_start": body.period_start.isoformat(),
            "period_end": body.period_end.isoformat(),
            "rebalance_freq": body.rebalance_freq,
            "n_positions": body.n_positions,
            "fee_bps": body.fee_bps,
            "slippage_bps": body.slippage_bps,
            "max_turnover_pct": body.max_turnover_pct,
            "n_trials": n_trials,
        },
    )
    queue_backtest_row(state, body=body, backtest_id=backtest_id, n_trials=n_trials)
    background.add_task(execute_backtest, state, body=body, run_id=run_id, backtest_id=backtest_id)
    state.bus.publish_nowait(
        "job_progress",
        {
            "job_run_id": run_id,
            "job_name": "backtest",
            "phase": "queued",
            "completed": 0,
            "total": 1,
            "eta_sec": None,
        },
    )
    return wrap(
        state,
        JobAccepted(
            job_run_id=run_id,
            status="queued",
            message_ja="バックテストを受け付けました。完了は SSE または GET /backtests で確認してください。",
            backtest_id=backtest_id,
        ),
    )


@router.get("/factor-weights", response_model=Envelope[FactorWeightsResponse])
def get_factor_weights(
    market: str = Query(default="JP"),
    horizon: str = Query(default="H20"),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[FactorWeightsResponse]:
    market = resolve_market(market)
    listed = state.sqlite.list_weight_sets(market=market, horizon=horizon)
    if listed:
        active_row = next((r for r in listed if r.is_active), None)
        others = [r for r in listed if not r.is_active]
        from packages.core.storage import to_dict

        return wrap(
            state,
            FactorWeightsResponse(
                market=market,  # type: ignore[arg-type]
                horizon=horizon,  # type: ignore[arg-type]
                active=_weight_set(to_dict(active_row, json_fields=("weights",)), is_active=True)
                if active_row
                else None,
                proposed=_weight_set(to_dict(others[0], json_fields=("weights",))) if others else None,
                history=[_weight_set(to_dict(r, json_fields=("weights",))) for r in listed],
            ),
        )
    raw = state.payload.get("factor_weights") or {}
    active = raw.get("active")
    proposed = raw.get("proposed")
    history = raw.get("history") or []
    return wrap(
        state,
        FactorWeightsResponse(
            market=raw.get("market") or market,
            horizon=raw.get("horizon") or horizon,
            active=_weight_set({**active, "market": market, "horizon": horizon}, is_active=True)
            if active
            else None,
            proposed=_weight_set({**proposed, "market": market, "horizon": horizon}) if proposed else None,
            history=[
                _weight_set({**h, "market": market, "horizon": horizon}) for h in history if h.get("weight_set_id")
            ],
        ),
    )


@router.post("/factor-weights/{weight_set_id}/activate", response_model=Envelope[OkResponse])
def activate_weights(
    weight_set_id: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[OkResponse]:
    ok = state.sqlite.activate_weight_set(weight_set_id)
    if not ok:
        raise not_found(f"重みセット {weight_set_id} は存在しません。")
    return wrap(state, OkResponse(ok=True, id=weight_set_id, message_ja="重みセットを有効化しました。"))
