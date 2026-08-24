"""銘柄詳細（docs/09-api-spec.md §2.4）。

`prices` は `series` でリサーチ用（J-Quants）と参考現在値（yfinance）を
明示的に分離する。レスポンスに必ず `source` と `is_delayed` を含める。
"""

from __future__ import annotations

import datetime as dt

from pydantic import Field

from packages.schemas.common import SchemaModel
from packages.schemas.enums import Market, PriceSeries


class Security(SchemaModel):
    """`securities` の現行行（docs/03-data-model.md §2.1）。"""

    ticker: str
    market: Market
    exchange: str | None = None
    exchange_ja: str | None = None
    name_local: str
    name_en: str | None = None
    sector_code: str | None = None
    sector_name: str | None = None
    industry_name: str | None = None
    currency: str
    cik: str | None = None
    edinet_code: str | None = None
    isin: str | None = None
    shares_outstanding: int | None = None
    trading_unit: int | None = None
    listing_date: dt.date | None = None
    delisting_date: dt.date | None = None
    is_active: bool = True


class KeyMetrics(SchemaModel):
    market_cap: float | None = None
    currency: str | None = None
    per_trailing: float | None = None
    per_forward: float | None = None
    pbr: float | None = None
    psr: float | None = None
    ev_ebitda: float | None = None
    dividend_yield: float | None = None
    fcf_yield: float | None = None
    earnings_yield: float | None = None
    roe: float | None = None
    roic: float | None = None
    equity_ratio: float | None = None
    debt_to_equity: float | None = None
    realized_vol_60d: float | None = None
    garch_vol: float | None = None
    adv_20d: float | None = None
    beta_market: float | None = None
    fx_sensitivity: float | None = None
    next_earnings_date: dt.date | None = None
    days_to_earnings: int | None = None
    financials_filed_at: dt.date | None = None


class StockDetail(SchemaModel):
    security: Security
    ref_price: float | None = None
    ref_change_pct: float | None = None
    ref_change_abs: float | None = None
    ref_source: str | None = None
    ref_as_of: dt.datetime | dt.date | None = None
    ref_is_delayed: bool = True
    ref_note_ja: str | None = None
    total_score: float | None = None
    quant_score: float | None = None
    conviction: str | None = None
    key_metrics: KeyMetrics | None = None


class PriceBar(SchemaModel):
    date: dt.date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None
    adj_close: float | None = None


class PriceOverlays(SchemaModel):
    ma20: float | None = None
    ma60: float | None = None
    ma200: float | None = None


class EventMarker(SchemaModel):
    date: dt.date
    label_ja: str


class RecommendationMarker(SchemaModel):
    date: dt.date
    action: str
    outcome: str


class PriceSeriesResponse(SchemaModel):
    ticker: str
    market: Market
    series: PriceSeries
    source: str
    is_delayed: bool
    delay_note_ja: str | None = None
    # research 系列をモデル学習に使ってよい。live 系列は禁止。
    model_use_forbidden: bool = False
    latest_as_of: dt.date | dt.datetime | None = None
    bars: list[PriceBar] = Field(default_factory=list)
    overlays: PriceOverlays | None = None
    earnings_markers: list[EventMarker] = Field(default_factory=list)
    recommendation_markers: list[RecommendationMarker] = Field(default_factory=list)


class FinancialPeriod(SchemaModel):
    """`financials` の 1 期（docs/03-data-model.md §2.4）。"""

    fiscal_period: str
    period_end: dt.date | None = None
    filed_at: dt.date
    source_doc_id: str | None = None
    revenue: float | None = None
    operating_income: float | None = None
    operating_margin: float | None = None
    ordinary_income: float | None = None
    net_income: float | None = None
    eps: float | None = None
    free_cash_flow: float | None = None
    operating_cf: float | None = None
    capex: float | None = None
    accruals_ratio: float | None = None
    net_debt_ebitda: float | None = None
    revenue_yoy: float | None = None
    operating_income_yoy: float | None = None
    forecast_revenue: float | None = None
    forecast_op_income: float | None = None
    forecast_net_income: float | None = None
    forecast_eps: float | None = None
    forecast_revised_at: dt.date | None = None
    accounting_standard: str | None = None
    currency: str | None = None
    is_restated: bool = False
    restated_note_ja: str | None = None


class FinancialsResponse(SchemaModel):
    ticker: str
    market: Market
    # PIT の基準。常に filed_at。
    basis: str = "filed_at"
    periods: list[FinancialPeriod] = Field(default_factory=list)


class FeatureRow(SchemaModel):
    """`features_daily` の 1 行を UI 向けに要約したもの。"""

    group: str
    label_ja: str
    z_score: float | None = None
    sector_percentile: float | None = None
    raw_label_ja: str | None = None
    sector_median_label_ja: str | None = None
    contribution: float | None = None


class FeaturesResponse(SchemaModel):
    ticker: str
    market: Market
    as_of: dt.date | None = None
    feature_version: str | None = None
    n_missing: int | None = None
    rows: list[FeatureRow] = Field(default_factory=list)


class PeerRow(SchemaModel):
    ticker: str
    market: Market | None = None
    name_local: str
    total_score: float | None = None
    per_forward: float | None = None
    pbr: float | None = None
    roic: float | None = None
    return_20d: float | None = None
    fx_sensitivity: float | None = None


class PeersResponse(SchemaModel):
    ticker: str
    market: Market
    sector_name: str | None = None
    peers: list[PeerRow] = Field(default_factory=list)


class SecuritySearchHit(SchemaModel):
    ticker: str
    market: Market
    name_local: str
    name_en: str | None = None
    sector_name: str | None = None


class SecuritySearchResult(SchemaModel):
    query: str
    items: list[SecuritySearchHit] = Field(default_factory=list)
    total: int = 0


__all__ = [
    "EventMarker",
    "FeatureRow",
    "FeaturesResponse",
    "FinancialPeriod",
    "FinancialsResponse",
    "KeyMetrics",
    "PeerRow",
    "PeersResponse",
    "PriceBar",
    "PriceOverlays",
    "PriceSeriesResponse",
    "RecommendationMarker",
    "Security",
    "SecuritySearchHit",
    "SecuritySearchResult",
    "StockDetail",
]
