"""特徴量計算・スコアリング。

すべての特徴量は `as_of` 時点で入手可能な情報のみから計算する。入口は
`pit_guard.PitContext` に固定してあり、生の DataFrame を直接渡す経路は用意しない。
"""

from packages.core.factors.calendar import (
    TRADING_DAYS_PER_YEAR,
    TradingCalendar,
    effective_date,
    next_business_day,
    shift_business_days,
)
from packages.core.factors.factor_config import FactorConfig, load_factor_config
from packages.core.factors.labels import build_label_panel, make_excess_label, make_label
from packages.core.factors.panel import PricePanel
from packages.core.factors.pipeline import (
    FEATURE_VERSION,
    build_pit_context,
    compute_features,
    compute_features_range,
    drop_incomplete,
    prepare_cross_section,
)
from packages.core.factors.pit_guard import (
    LeakError,
    PitContext,
    PitFrame,
    assert_monotonic_availability,
    assert_no_future_rows,
    assert_stable_under_future_data,
    future_rows_like,
    latest_available,
)
from packages.core.factors.registry import (
    FEATURE_COLUMNS,
    REGISTRY,
    FactorSpec,
    by_category,
    spec,
)
from packages.core.factors.scoring import (
    compute_group_z,
    compute_quant_score,
    is_candidate,
    score_cross_section,
    total_score,
)
from packages.core.factors.screening import (
    REASON_CODES,
    HitRatePrior,
    UniverseFilter,
    apply_preset,
    apply_risk_constraints,
    assign_reason_codes,
    select_recommendation_candidates,
    compute_hit_rate_prior,
    conviction_from_score,
    determine_action,
)
from packages.core.factors.transforms import (
    mad_std,
    robust_zscore,
    sector_neutral_zscore,
    winsorize,
)

__all__ = [
    "FEATURE_COLUMNS",
    "FEATURE_VERSION",
    "REASON_CODES",
    "REGISTRY",
    "TRADING_DAYS_PER_YEAR",
    "FactorConfig",
    "FactorSpec",
    "HitRatePrior",
    "LeakError",
    "PitContext",
    "PitFrame",
    "PricePanel",
    "TradingCalendar",
    "UniverseFilter",
    "apply_preset",
    "apply_risk_constraints",
    "assert_monotonic_availability",
    "assert_no_future_rows",
    "assert_stable_under_future_data",
    "assign_reason_codes",
    "build_label_panel",
    "build_pit_context",
    "by_category",
    "compute_features",
    "compute_features_range",
    "compute_group_z",
    "compute_hit_rate_prior",
    "compute_quant_score",
    "conviction_from_score",
    "determine_action",
    "drop_incomplete",
    "effective_date",
    "future_rows_like",
    "is_candidate",
    "latest_available",
    "load_factor_config",
    "mad_std",
    "make_excess_label",
    "make_label",
    "next_business_day",
    "prepare_cross_section",
    "robust_zscore",
    "score_cross_section",
    "select_recommendation_candidates",
    "sector_neutral_zscore",
    "shift_business_days",
    "spec",
    "total_score",
    "winsorize",
]
