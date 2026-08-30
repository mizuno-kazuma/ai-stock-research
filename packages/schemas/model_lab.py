"""モデルラボ（docs/09-api-spec.md §2.7, docs/03-data-model.md §2.13-2.14）。

`POST /backtests` は fee_bps / slippage_bps / max_turnover_pct / n_trials を必須にする。
**API レベルでもデフォルト値を持たせない。** ゼロコストのバックテストを
うっかり実行できないようにするための構造的制約である。
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import Field

from packages.schemas.common import SchemaModel
from packages.schemas.enums import Horizon, Market, ModelKind, RebalanceFreq


class ModelRun(SchemaModel):
    run_id: str
    model_kind: ModelKind
    model_version: str | None = None
    market: Market | None = None
    horizon: Horizon | None = None
    train_start: dt.date | None = None
    train_end: dt.date | None = None
    valid_start: dt.date | None = None
    valid_end: dt.date | None = None
    cv_scheme: str = "purged_walk_forward"
    purge_days: int | None = None
    embargo_days: int | None = None
    n_folds: int | None = None
    feature_version: str | None = None
    feature_list: list[str] = Field(default_factory=list)
    hyperparams: dict[str, Any] | None = None
    input_snapshot_hash: str | None = None
    metrics: dict[str, Any] | None = None
    # DSR の計算に必要。記録しないと多重検定バイアスを定量化できない。
    n_trials: int | None = None
    fold_rank_ic: list[float] = Field(default_factory=list)
    fold_ic_std: float | None = None
    artifact_path: str | None = None
    git_commit: str | None = None
    started_at: dt.datetime | None = None
    finished_at: dt.datetime | None = None
    status: str = "success"


class ModelRunList(SchemaModel):
    items: list[ModelRun]
    total: int


class FeatureImportance(SchemaModel):
    feature: str
    label_ja: str | None = None
    gain: float


class FeatureImportanceResponse(SchemaModel):
    run_id: str
    items: list[FeatureImportance] = Field(default_factory=list)


class IcPoint(SchemaModel):
    as_of: dt.date
    rank_ic: float | None = None


class IcTimeseries(SchemaModel):
    run_id: str
    points: list[IcPoint] = Field(default_factory=list)
    mean_ic: float | None = None
    std_ic: float | None = None
    t_stat: float | None = None


class Quintile(SchemaModel):
    quintile: int
    label_ja: str | None = None
    mean_excess_return: float | None = None


class ValidationSpec(SchemaModel):
    method: str = "PurgedWalkForwardCV"
    n_folds: int | None = None
    train_window_days: int | None = None
    test_window_days: int | None = None
    purge_days: int | None = None
    embargo_days: int | None = None
    expanding: bool | None = None


class ModelHealth(SchemaModel):
    market: Market
    horizon: Horizon
    as_of: dt.date | None = None
    rank_ic_20d: float | None = None
    rank_ic_20d_n: int | None = None
    rank_ic_3m: float | None = None
    rank_ic_3m_n: int | None = None
    rank_ic_3m_tstat: float | None = None
    rank_ic_percentile_1y: float | None = None
    coverage_pct: float | None = None
    covered_tickers: int | None = None
    universe_tickers: int | None = None
    degradation_detected: bool = False
    ic_mean_period: float | None = None
    ic_std_period: float | None = None
    ic_positive_days_pct: float | None = None
    ic_n_days: int | None = None
    quintiles: list[Quintile] = Field(default_factory=list)
    quintile_spread: float | None = None
    monotonic: bool | None = None
    feature_importance: list[FeatureImportance] = Field(default_factory=list)
    validation: ValidationSpec | None = None
    status: str = "normal"
    coverage_note_ja: str | None = None


class UniverseFilterSpec(SchemaModel):
    min_adv_20d: float | None = None
    min_market_cap: float | None = None
    exclude_sectors: list[str] = Field(default_factory=list)
    exclude_recently_listed_days: int | None = None


class SignalSource(SchemaModel):
    type: str
    weight_set_id: str | None = None
    model_run_id: str | None = None


class BacktestRequest(SchemaModel):
    """コストパラメータを必須にする（デフォルト値を持たせない）。"""

    strategy_name: str
    market: Market
    period_start: dt.date
    period_end: dt.date
    rebalance_freq: RebalanceFreq
    n_positions: int = Field(ge=1)
    fee_bps: float = Field(ge=0.0)
    slippage_bps: float = Field(ge=0.0)
    max_turnover_pct: float = Field(gt=0.0)
    signal_source: SignalSource | None = None
    universe_filter: UniverseFilterSpec | None = None
    n_trials: int = Field(ge=1)


class BacktestRun(SchemaModel):
    backtest_id: str
    strategy_name: str
    market: Market
    status: str
    model_run_id: str | None = None
    period_start: dt.date
    period_end: dt.date
    rebalance_freq: RebalanceFreq
    n_positions: int
    fee_bps: float
    slippage_bps: float
    max_turnover_pct: float

    total_return: float | None = None
    cagr: float | None = None
    annualized_return: float | None = None
    benchmark_annualized: float | None = None
    excess_return: float | None = None
    volatility: float | None = None
    sharpe: float | None = None
    sortino: float | None = None
    max_drawdown: float | None = None
    max_drawdown_period_ja: str | None = None
    calmar: float | None = None
    hit_rate: float | None = None
    monthly_hit_rate: float | None = None
    n_months: int | None = None
    profit_factor: float | None = None
    avg_turnover: float | None = None
    realized_turnover_pct: float | None = None
    total_cost_bps: float | None = None
    cost_drag_annual: float | None = None
    gross_annualized_return: float | None = None
    benchmark_return: float | None = None
    alpha_vs_bench: float | None = None
    information_ratio: float | None = None
    skew: float | None = None
    kurtosis: float | None = None

    n_trials: int | None = None
    deflated_sharpe: float | None = None
    dsr_pvalue: float | None = None
    is_significant: bool | None = None
    significance_ja: str | None = None

    progress_pct: float | None = None
    elapsed_sec: float | None = None
    eta_sec: float | None = None
    error_ja: str | None = None
    config: dict[str, Any] | None = None
    git_commit: str | None = None
    run_at: dt.datetime | None = None


class BacktestList(SchemaModel):
    items: list[BacktestRun]
    total: int


class EquityCurvePoint(SchemaModel):
    date: dt.date
    equity: float
    benchmark: float | None = None
    drawdown: float | None = None


class EquityCurve(SchemaModel):
    backtest_id: str
    points: list[EquityCurvePoint] = Field(default_factory=list)


class BacktestTrade(SchemaModel):
    ticker: str
    market: Market | None = None
    entry_date: dt.date
    exit_date: dt.date | None = None
    entry_price: float | None = None
    exit_price: float | None = None
    quantity: float | None = None
    pnl: float | None = None
    return_pct: float | None = None
    cost_bps: float | None = None


class BacktestTradeList(SchemaModel):
    backtest_id: str
    items: list[BacktestTrade] = Field(default_factory=list)
    total: int = 0


class JobAccepted(SchemaModel):
    """202 Accepted のレスポンス（docs/09-api-spec.md §2.7）。"""

    job_run_id: int
    status: str = "queued"
    message_ja: str | None = None
    backtest_id: str | None = None


class FactorWeightSet(SchemaModel):
    weight_set_id: str
    market: Market
    horizon: Horizon
    weights: dict[str, float]
    fitted_from: dt.date | None = None
    fitted_to: dt.date | None = None
    fit_method: str | None = None
    ic_in_sample: float | None = None
    ic_out_of_sample: float | None = None
    n_samples: int | None = None
    blend_ratio: float | None = None
    period_ja: str | None = None
    is_active: bool = False
    status: str | None = None
    activated_at: dt.datetime | dt.date | None = None
    deactivated_at: dt.datetime | dt.date | None = None
    created_by: str | None = None
    created_at: dt.datetime | dt.date | None = None
    proposed_at: dt.datetime | dt.date | None = None


class FactorWeightsResponse(SchemaModel):
    market: Market
    horizon: Horizon
    active: FactorWeightSet | None = None
    proposed: FactorWeightSet | None = None
    history: list[FactorWeightSet] = Field(default_factory=list)


__all__ = [
    "BacktestList",
    "BacktestRequest",
    "BacktestRun",
    "BacktestTrade",
    "BacktestTradeList",
    "EquityCurve",
    "EquityCurvePoint",
    "FactorWeightSet",
    "FactorWeightsResponse",
    "FeatureImportance",
    "FeatureImportanceResponse",
    "IcPoint",
    "IcTimeseries",
    "JobAccepted",
    "ModelHealth",
    "ModelRun",
    "ModelRunList",
    "Quintile",
    "SignalSource",
    "UniverseFilterSpec",
    "ValidationSpec",
]
