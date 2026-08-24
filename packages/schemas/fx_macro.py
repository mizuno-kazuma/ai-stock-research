"""為替・マクロ（docs/09-api-spec.md §2.6, docs/03-data-model.md §2.11-2.12）。

為替のレスポンスには必ず全モデルの予測とベースライン比較を含める。
`verdict_ja` は API 側で生成する。UI が判定ロジックを持たないようにすることで、
「優位性がないのに強気に表示する」実装ミスを構造的に防ぐ。
"""

from __future__ import annotations

import datetime as dt

from pydantic import Field

from packages.schemas.common import SchemaModel


class FxForecast(SchemaModel):
    horizon_days: int
    horizon: str | None = None
    label_ja: str | None = None
    model_id: str
    point: float
    ci_lo_80: float
    ci_hi_80: float
    ci_lo_95: float | None = None
    ci_hi_95: float | None = None
    change_pct: float | None = None
    is_baseline: bool = False
    dm_statistic: float | None = None
    dm_pvalue: float | None = None
    beats_baseline: bool | None = None
    rmse_oos_60d: float | None = None
    baseline_rmse_oos_60d: float | None = None
    directional_accuracy_60d: float | None = None
    n_validation: int | None = None
    verdict_ja: str | None = None


class FxVolForecast(SchemaModel):
    garch_vol_1d_ann: float | None = None
    garch_vol_20d_ann: float | None = None
    realized_vol_20d: float | None = None
    realized_vol_60d: float | None = None
    persistence: float | None = None
    converged: bool | None = None
    regime_ja: str | None = None


class Cointegration(SchemaModel):
    tested_pairs: list[str] = Field(default_factory=list)
    rank: int | None = None
    detected: bool = False
    note_ja: str | None = None


class RateDifferential(SchemaModel):
    us_10y: float | None = None
    jp_10y: float | None = None
    diff: float | None = None
    us_2y: float | None = None
    jp_2y: float | None = None
    diff_2y: float | None = None
    percentile_5y: float | None = None
    correlation_1y: float | None = None


class DieboldMariano(SchemaModel):
    stat: float | None = None
    p_value: float | None = None
    n_validation: int | None = None
    variance: str | None = None
    hac_lags: int | None = None


class ModelComparisonRow(SchemaModel):
    model_id: str
    label_ja: str | None = None
    is_baseline: bool = False
    rmse: float | None = None
    mae: float | None = None
    direction_hit_rate: float | None = None
    n: int | None = None
    dm_p_value: float | None = None
    verdict_ja: str | None = None


class FxQuote(SchemaModel):
    value: float
    as_of: dt.date | dt.datetime
    source: str
    change_pct: float | None = None
    change_abs: float | None = None
    delay_minutes: int | None = None


class FxDetail(SchemaModel):
    pair: str
    as_of: dt.date
    spot: float | None = None
    official: FxQuote | None = None
    reference: FxQuote | None = None
    # UI が判定しないよう、文言は API で確定させる。
    verdict_ja: str
    verdict_status: str
    diebold_mariano: DieboldMariano | None = None
    baseline_rmse: float | None = None
    model_rmse: float | None = None
    forecasts: list[FxForecast] = Field(default_factory=list)
    model_comparison: list[ModelComparisonRow] = Field(default_factory=list)
    vol_forecast: FxVolForecast | None = None
    cointegration: Cointegration | None = None
    rate_differential: RateDifferential | None = None


class FxHistoryPoint(SchemaModel):
    date: dt.date
    value: float


class FxHistory(SchemaModel):
    pair: str
    range: str
    source: str
    points: list[FxHistoryPoint] = Field(default_factory=list)


class MacroPoint(SchemaModel):
    observation_date: dt.date
    value: float | None = None
    vintage_date: dt.date | None = None


class MacroSeries(SchemaModel):
    series_id: str
    label_ja: str | None = None
    unit: str | None = None
    frequency: str | None = None
    latest: float | None = None
    change_mom: float | None = None
    as_of: dt.date | None = None
    vintage_date: dt.date | None = None
    revised: bool = False
    revision_note_ja: str | None = None
    points: list[MacroPoint] = Field(default_factory=list)


class MacroSeriesResponse(SchemaModel):
    range: str
    series: list[MacroSeries] = Field(default_factory=list)


class RateDifferentialPoint(SchemaModel):
    date: dt.date
    spread_10y: float | None = None
    usdjpy: float | None = None


class RateDifferentialResponse(SchemaModel):
    range: str
    current: RateDifferential | None = None
    correlation_1y: float | None = None
    points: list[RateDifferentialPoint] = Field(default_factory=list)


__all__ = [
    "Cointegration",
    "DieboldMariano",
    "FxDetail",
    "FxForecast",
    "FxHistory",
    "FxHistoryPoint",
    "FxQuote",
    "FxVolForecast",
    "MacroPoint",
    "MacroSeries",
    "MacroSeriesResponse",
    "ModelComparisonRow",
    "RateDifferential",
    "RateDifferentialPoint",
    "RateDifferentialResponse",
]
