"""推奨カード（docs/09-api-spec.md §2.2, docs/03-data-model.md §2.9）。

`bear_case_ja` / `expected_ret_lo` / `expected_ret_hi` / `citations` /
`source_doc_ids` を Optional にしないことが、この型の要点である。
表示側で「弱気論拠がない状態」を作れないようにする。
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import Field, field_validator

from packages.schemas.common import DataFreshness, SchemaModel
from packages.schemas.enums import (
    Action,
    CitationVerification,
    Conviction,
    CriticVerdict,
    DocType,
    FeedbackVerdict,
    Horizon,
    Market,
)

DisplayTier = Literal["core", "fill", "score_only"]
MIN_VISIBLE_RECOMMENDATIONS = 10

BEAR_CASE_MIN_LEN = 20


class Citation(SchemaModel):
    """引用。doc_id + ページ + 原文引用の 3 点が揃っていること。"""

    doc_id: str
    page: int | None = None
    quote: str
    doc_type: DocType | None = None
    title: str | None = None
    filed_at: dt.date | dt.datetime | None = None
    verification: CitationVerification | None = None


class FactorScores(SchemaModel):
    """ファクターグループごとの z-score。欠損は null（0 で埋めない）。"""

    value: float | None = None
    momentum: float | None = None
    quality: float | None = None
    growth: float | None = None
    lowvol: float | None = None
    liquidity: float | None = None
    revision: float | None = None
    # docs/ui/sample-data.json は lowvol を volatility と呼んでいる。
    # 両方を受けられるようにするが、API が返すのは lowvol 側に寄せる。
    volatility: float | None = None


class PastPerformance(SchemaModel):
    n: int
    hit_rate: float | None = None
    avg_excess_return: float | None = None
    max_drawdown: float | None = None
    period_ja: str | None = None


class RecommendationSummary(SchemaModel):
    """ダッシュボードの上位推奨など、一覧表示用の要約。"""

    rec_id: str
    as_of: dt.date
    ticker: str
    market: Market
    name_local: str
    sector_name: str | None = None
    action: Action
    horizon: Horizon
    conviction: Conviction
    conviction_score: float
    total_score: float | None = None
    expected_ret: float | None = None
    expected_ret_lo: float | None = None
    expected_ret_hi: float | None = None
    hit_rate_prior: float | None = None
    n_prior_samples: int | None = None
    reason_codes: list[str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)


class RecommendationCard(SchemaModel):
    """推奨カードの全フィールド（docs/09-api-spec.md §2.2）。"""

    rec_id: str
    as_of: dt.date
    ticker: str
    market: Market
    name_local: str
    name_en: str | None = None
    sector_code: str | None = None
    sector_name: str | None = None

    action: Action
    horizon: Horizon
    conviction: Conviction
    conviction_score: float

    thesis_ja: str
    bear_case_ja: str
    invalidation_ja: str

    reason_codes: list[str] = Field(min_length=1)

    expected_ret: float | None = None
    expected_ret_lo: float
    expected_ret_hi: float
    hit_rate_prior: float | None = None
    n_prior_samples: int | None = None

    quant_score: float | None = None
    quant_rank: int | None = None
    quant_percentile: float | None = None
    qual_score: float | None = None
    qual_confidence: float | None = None
    qual_doc_count: int | None = None
    qual_delta: float | None = None
    total_score: float | None = None
    ml_pred: float | None = None

    factor_scores: FactorScores | None = None

    entry_ref_price: float | None = None
    entry_ref_source: str | None = None
    entry_ref_note_ja: str | None = None
    stop_ref_price: float | None = None
    target_ref_price: float | None = None
    suggested_size_pct: float | None = None
    currency: str | None = None

    source_doc_ids: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(min_length=1)

    data_freshness: list[DataFreshness] = Field(default_factory=list)
    past_performance: PastPerformance | None = None
    critic_verdict: CriticVerdict | None = None
    critic_notes_ja: str | None = None
    memory_ids_used: list[int | str] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    generated_at: dt.datetime

    @field_validator("bear_case_ja")
    @classmethod
    def bear_case_must_be_substantial(cls, v: str) -> str:
        """空・短すぎる弱気論拠を型のレベルで拒否する。

        docs/03-data-model.md §2.9 の不変条件 1 と同じ規則。
        リポジトリ層でも同じ検証を行う（二重に持つのは意図的）。
        """
        if len(v.strip()) < BEAR_CASE_MIN_LEN:
            raise ValueError(
                f"bear_case_ja は {BEAR_CASE_MIN_LEN} 文字以上必要です（現在 {len(v.strip())} 文字）"
            )
        return v


class RecommendationFeedItem(SchemaModel):
    """スコア済みユニバースの 1 行。推奨カードがあれば付ける。

    カードがない行でも `name_local` とスコア（`total_score` または `quant_score`）
    は必須。ティッカーだけの行にはしない。
    """

    ticker: str
    market: Market
    as_of: dt.date
    name_local: str
    sector_code: str | None = None
    sector_name: str | None = None
    display_tier: DisplayTier
    total_score: float | None = None
    quant_score: float | None = None
    quant_rank: int | None = None
    quant_percentile: float | None = None
    ml_pred_h20: float | None = None
    ml_pred_h20_lo: float | None = None
    ml_pred_h20_hi: float | None = None
    reason_codes: list[str] = Field(default_factory=list)
    critic_verdict: CriticVerdict | None = None
    rec_id: str | None = None
    action: Action | None = None
    horizon: Horizon | None = None
    conviction: Conviction | None = None
    card: RecommendationCard | None = None

    @field_validator("name_local")
    @classmethod
    def name_local_must_be_present(cls, v: str) -> str:
        name = v.strip()
        if not name:
            raise ValueError("カードなし行でも name_local（会社名）は必須です")
        return name


class RecommendationList(SchemaModel):
    items: list[RecommendationFeedItem]
    total: int
    universe_size: int = 0
    filled_count: int = 0
    limit: int | None = None
    offset: int | None = None


class RecommendationOutcome(SchemaModel):
    """実績（docs/03-data-model.md §2.10）。"""

    rec_id: str
    horizon: Horizon
    evaluated_at: dt.datetime
    entry_date: dt.date
    exit_date: dt.date
    entry_price: float
    exit_price: float
    raw_return: float
    benchmark_return: float
    excess_return: float
    sector_excess_return: float | None = None
    is_hit: bool
    max_favorable_excursion: float | None = None
    max_adverse_excursion: float | None = None
    realized_vol: float | None = None
    notes_ja: str | None = None


class RecommendationFeedbackRequest(SchemaModel):
    verdict: FeedbackVerdict
    note_ja: str | None = None


class RecommendationHistoryRow(SchemaModel):
    rec_id: str
    generated_at: dt.date | dt.datetime
    action: Action
    horizon: Horizon
    conviction: Conviction
    expected_ret: float | None = None
    expected_ret_lo: float | None = None
    expected_ret_hi: float | None = None
    realized_ret: float | None = None
    outcome: str
    pending_business_days_left: int | None = None


class RecommendationHistory(SchemaModel):
    ticker: str
    market: Market
    n: int
    hit_rate: float | None = None
    avg_excess_return: float | None = None
    rows: list[RecommendationHistoryRow] = Field(default_factory=list)


__all__ = [
    "BEAR_CASE_MIN_LEN",
    "MIN_VISIBLE_RECOMMENDATIONS",
    "Citation",
    "DisplayTier",
    "FactorScores",
    "PastPerformance",
    "RecommendationCard",
    "RecommendationFeedItem",
    "RecommendationFeedbackRequest",
    "RecommendationHistory",
    "RecommendationHistoryRow",
    "RecommendationList",
    "RecommendationOutcome",
    "RecommendationSummary",
]
