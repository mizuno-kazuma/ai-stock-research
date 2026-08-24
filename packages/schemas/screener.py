"""スコアとスクリーナー（docs/09-api-spec.md §2.3）。"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import Field

from packages.schemas.common import SchemaModel
from packages.schemas.enums import FilterOp, Market, SortDir

SCREENER_MAX_ROWS = 500


class ScoreRow(SchemaModel):
    """`scores_daily` の 1 行（docs/03-data-model.md §2.8）。"""

    ticker: str
    market: Market
    as_of: dt.date
    name_local: str | None = None
    sector_code: str | None = None
    sector_name: str | None = None

    value_z: float | None = None
    momentum_z: float | None = None
    quality_z: float | None = None
    growth_z: float | None = None
    lowvol_z: float | None = None
    liquidity_z: float | None = None
    revision_z: float | None = None

    quant_score: float | None = None
    quant_rank: int | None = None
    quant_percentile: float | None = None
    sector_rank: int | None = None

    qual_score: float | None = None
    qual_confidence: float | None = None
    qual_doc_count: int | None = None

    total_score: float | None = None
    ml_pred_h5: float | None = None
    ml_pred_h20: float | None = None
    ml_pred_h5_lo: float | None = None
    ml_pred_h5_hi: float | None = None
    ml_pred_h20_lo: float | None = None
    ml_pred_h20_hi: float | None = None

    weight_set_id: str | None = None
    feature_version: str | None = None
    model_run_id: str | None = None
    computed_at: dt.datetime | None = None


class ScoreList(SchemaModel):
    items: list[ScoreRow]
    total: int
    limit: int | None = None
    offset: int | None = None


class ScreenerFilter(SchemaModel):
    field: str
    op: FilterOp
    # `in` / `between` では配列、`is_null` では省略可。
    value: Any | None = None


class ScreenerSort(SchemaModel):
    field: str
    dir: SortDir = "desc"


class ScreenerRequest(SchemaModel):
    market: Market = "JP"
    as_of: dt.date | None = None
    filters: list[ScreenerFilter] = Field(default_factory=list)
    sort: list[ScreenerSort] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    limit: int = Field(default=100, ge=1, le=SCREENER_MAX_ROWS)
    offset: int = Field(default=0, ge=0)


class ScreenerDistribution(SchemaModel):
    field: str
    label_ja: str | None = None
    median: float | None = None
    threshold: float | None = None
    threshold_percentile: float | None = None


class ScreenerResult(SchemaModel):
    as_of: dt.date | None = None
    market: Market
    columns: list[str]
    rows: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
    # 500 件で打ち切った場合に true（docs/09-api-spec.md §2.3）
    truncated: bool = False
    universe_size: int | None = None
    excluded_count: int | None = None
    excluded_reason_ja: str | None = None
    distributions: list[ScreenerDistribution] = Field(default_factory=list)


class ScreenerPreset(SchemaModel):
    """docs/05-scoring-screening.md §9.2。"""

    preset_id: str
    name_ja: str
    description_ja: str | None = None
    market: Market | None = None
    filters: list[ScreenerFilter] = Field(default_factory=list)
    sort: list[ScreenerSort] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)


class SavedScreen(SchemaModel):
    id: str
    name_ja: str
    request: ScreenerRequest
    created_at: dt.datetime


class SavedScreenCreate(SchemaModel):
    name_ja: str
    request: ScreenerRequest


__all__ = [
    "SCREENER_MAX_ROWS",
    "SavedScreen",
    "SavedScreenCreate",
    "ScoreList",
    "ScoreRow",
    "ScreenerDistribution",
    "ScreenerFilter",
    "ScreenerPreset",
    "ScreenerRequest",
    "ScreenerResult",
    "ScreenerSort",
]
