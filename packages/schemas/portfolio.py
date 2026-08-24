"""ポートフォリオ・売買日誌（docs/09-api-spec.md §2.9）。

`GET /trades/analysis` は「推奨の質」と「実行の質」を分離して返す。
この切り分けができないと改善対象が特定できない。
"""

from __future__ import annotations

import datetime as dt

from pydantic import Field

from packages.schemas.common import SchemaModel
from packages.schemas.enums import EmotionTag, Market, Side


class Position(SchemaModel):
    ticker: str
    market: Market
    name_local: str | None = None
    sector_name: str | None = None
    account_type: str | None = None
    quantity: float
    avg_cost: float
    currency: str
    book_value_jpy: float | None = None
    ref_price: float | None = None
    market_value_jpy: float | None = None
    unrealized_pl_jpy: float | None = None
    unrealized_pl_pct: float | None = None
    weight: float | None = None
    total_score: float | None = None
    current_view: str | None = None
    current_view_label_ja: str | None = None
    holding_days: int | None = None
    next_earnings_date: dt.date | None = None
    opened_at: dt.datetime | dt.date | None = None
    is_open: bool = True


class PositionList(SchemaModel):
    items: list[Position]
    total: int


class SectorAllocation(SchemaModel):
    sector_name: str
    weight: float
    n: int


class PortfolioRisk(SchemaModel):
    top_position_weight: float | None = None
    top_position_ticker: str | None = None
    top3_weight: float | None = None
    top_sector_weight: float | None = None
    top_sector_name: str | None = None
    usd_exposure: float | None = None
    weighted_fx_sensitivity: float | None = None
    high_vol_share: float | None = None
    positions_reporting_soon: int | None = None
    warnings_ja: list[str] = Field(default_factory=list)


class PortfolioPerformance(SchemaModel):
    range: str
    portfolio_return: float | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    benchmark_label_ja: str | None = None


class Portfolio(SchemaModel):
    as_of: dt.date | None = None
    base_currency: str = "JPY"
    market_value_jpy: float | None = None
    book_value_jpy: float | None = None
    unrealized_pl_jpy: float | None = None
    unrealized_pl_pct: float | None = None
    realized_pl_ytd_jpy: float | None = None
    cash_jpy: float | None = None
    daily_pl_jpy: float | None = None
    daily_pl_pct: float | None = None
    currency_split: dict[str, float] = Field(default_factory=dict)
    fx_rate_used: float | None = None
    n_positions: int = 0
    performance: PortfolioPerformance | None = None
    allocation_by_sector: list[SectorAllocation] = Field(default_factory=list)
    risk: PortfolioRisk | None = None


class Trade(SchemaModel):
    trade_id: str
    ticker: str
    market: Market
    name_local: str | None = None
    side: Side
    quantity: float
    price: float
    fee: float = 0.0
    currency: str
    executed_at: dt.datetime
    broker: str | None = None
    account_type: str | None = None
    linked_rec_id: str | None = None
    thesis_ja: str | None = None
    emotion_tag: EmotionTag | None = None
    exit_plan_ja: str | None = None
    review_ja: str | None = None
    ref_price_at_entry: float | None = None
    slippage_bps: float | None = None
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None


class TradeCreate(SchemaModel):
    ticker: str
    market: Market
    side: Side
    quantity: float = Field(gt=0)
    price: float = Field(ge=0)
    fee: float = 0.0
    currency: str
    executed_at: dt.datetime
    broker: str | None = None
    account_type: str | None = None
    linked_rec_id: str | None = None
    thesis_ja: str | None = None
    emotion_tag: EmotionTag | None = None
    exit_plan_ja: str | None = None
    review_ja: str | None = None


class TradePatch(SchemaModel):
    quantity: float | None = None
    price: float | None = None
    fee: float | None = None
    executed_at: dt.datetime | None = None
    broker: str | None = None
    account_type: str | None = None
    linked_rec_id: str | None = None
    thesis_ja: str | None = None
    emotion_tag: EmotionTag | None = None
    exit_plan_ja: str | None = None
    review_ja: str | None = None


class TradeList(SchemaModel):
    items: list[Trade]
    total: int
    limit: int | None = None
    offset: int | None = None


class TradeImportResult(SchemaModel):
    n_rows: int
    n_imported: int
    n_skipped: int
    errors_ja: list[str] = Field(default_factory=list)


class RecommendationQuality(SchemaModel):
    n_recommendations: int
    hit_rate: float | None = None
    avg_excess_return: float | None = None
    by_conviction: dict[str, float] = Field(default_factory=dict)
    by_conviction_n: dict[str, int] = Field(default_factory=dict)
    monotonic: bool | None = None
    note_ja: str | None = None
    scope_note_ja: str | None = None


class ExecutionQuality(SchemaModel):
    n_trades: int
    n_from_recommendation: int
    n_discretionary: int
    hit_rate_from_rec: float | None = None
    hit_rate_discretionary: float | None = None
    avg_slippage_vs_ref_bps: float | None = None
    buy_slippage_bps: float | None = None
    sell_slippage_bps: float | None = None
    avg_holding_days: float | None = None
    planned_holding_days: float | None = None
    median_holding_days_winners: float | None = None
    median_holding_days_losers: float | None = None
    exited_early_pct: float | None = None
    exited_early_n: int | None = None
    held_longer_pct: float | None = None
    held_longer_n: int | None = None
    exit_plan_adherence: float | None = None
    exit_plan_adherence_n: int | None = None
    by_emotion_tag: dict[str, float] = Field(default_factory=dict)
    by_emotion_tag_n: dict[str, int] = Field(default_factory=dict)
    note_ja: str | None = None
    observations_ja: list[str] = Field(default_factory=list)


class JournalStats(SchemaModel):
    n_entries: int
    thesis_filled_pct: float | None = None
    emotion_tagged_pct: float | None = None
    exit_plan_filled_pct: float | None = None
    exit_plan_denominator: int | None = None
    linked_to_rec_pct: float | None = None


class TradeAnalysis(SchemaModel):
    recommendation_quality: RecommendationQuality
    execution_quality: ExecutionQuality
    journal_stats: JournalStats | None = None


__all__ = [
    "ExecutionQuality",
    "JournalStats",
    "Portfolio",
    "PortfolioPerformance",
    "PortfolioRisk",
    "Position",
    "PositionList",
    "RecommendationQuality",
    "SectorAllocation",
    "Trade",
    "TradeAnalysis",
    "TradeCreate",
    "TradeImportResult",
    "TradeList",
    "TradePatch",
]
