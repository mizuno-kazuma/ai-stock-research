"""ダッシュボード（docs/09-api-spec.md §2.1）。"""

from __future__ import annotations

import datetime as dt

from pydantic import Field

from packages.schemas.common import SchemaModel
from packages.schemas.enums import JobStatus, Market, Severity
from packages.schemas.recommendations import RecommendationFeedItem


class BenchmarkQuote(SchemaModel):
    symbol: str
    label_ja: str | None = None
    close: float | None = None
    change_pct: float | None = None
    change_abs: float | None = None
    as_of: dt.date | dt.datetime | None = None


class AdvanceDecline(SchemaModel):
    advancing: int
    declining: int
    unchanged: int


class VolRegime(SchemaModel):
    level: str
    percentile: float | None = None
    message_ja: str | None = None


class CorrelationRegime(SchemaModel):
    avg_pairwise_corr_60d: float | None = None
    level: str | None = None


class MarketSummary(SchemaModel):
    benchmark: BenchmarkQuote | None = None
    advance_decline: AdvanceDecline | None = None
    vol_regime: VolRegime | None = None
    correlation_regime: CorrelationRegime | None = None


class FxForecastBrief(SchemaModel):
    point: float | None = None
    ci_lo_80: float | None = None
    ci_hi_80: float | None = None
    beats_baseline: bool | None = None
    note_ja: str | None = None


class DashboardFx(SchemaModel):
    pair: str
    spot: float | None = None
    change_pct: float | None = None
    as_of: dt.date | dt.datetime | None = None
    forecast_h20: FxForecastBrief | None = None


class TopMover(SchemaModel):
    ticker: str
    market: Market | None = None
    name_local: str | None = None
    change_pct: float | None = None


class PortfolioSnapshot(SchemaModel):
    n_positions: int
    unrealized_pnl_pct: float | None = None
    day_change_pct: float | None = None
    market_value: float | None = None
    currency: str = "JPY"
    top_movers: list[TopMover] = Field(default_factory=list)


class ModelHealthBrief(SchemaModel):
    rank_ic_20d: float | None = None
    rank_ic_percentile_1y: float | None = None
    status: str = "unknown"
    coverage_rate: float | None = None
    coverage_note_ja: str | None = None


class Alert(SchemaModel):
    alert_id: str
    severity: Severity
    category: str
    title_ja: str
    body_ja: str | None = None
    entity: str | None = None
    is_read: bool = False
    created_at: dt.datetime
    link: str | None = None


class WatchlistFiling(SchemaModel):
    doc_id: str
    ticker: str | None = None
    market: Market | None = None
    name_local: str | None = None
    doc_type: str
    title: str
    filed_at: dt.datetime
    has_summary: bool = False


class JobStatusBrief(SchemaModel):
    last_run: dt.datetime | None = None
    status: JobStatus | None = None
    failed_steps: list[str] = Field(default_factory=list)


class Dashboard(SchemaModel):
    as_of: dt.date | None = None
    market: Market = "JP"
    market_summary: MarketSummary | None = None
    fx: DashboardFx | None = None
    top_recommendations: list[RecommendationFeedItem] = Field(default_factory=list)
    portfolio_snapshot: PortfolioSnapshot | None = None
    new_filings_count: int = 0
    watchlist_filings: list[WatchlistFiling] = Field(default_factory=list)
    model_health: ModelHealthBrief | None = None
    alerts: list[Alert] = Field(default_factory=list)
    job_status: JobStatusBrief | None = None


__all__ = [
    "AdvanceDecline",
    "Alert",
    "BenchmarkQuote",
    "CorrelationRegime",
    "Dashboard",
    "DashboardFx",
    "FxForecastBrief",
    "JobStatusBrief",
    "MarketSummary",
    "ModelHealthBrief",
    "PortfolioSnapshot",
    "TopMover",
    "VolRegime",
    "WatchlistFiling",
]
