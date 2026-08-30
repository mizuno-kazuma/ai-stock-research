"""予測モデル（GARCH / ARIMAX / クロスセクショナル・ランカー）。

すべての予測は点推定 + 信頼区間を返す。交差検証は Purged Walk-Forward のみ。
"""

from packages.core.models.arimax import (
    DMResult,
    Forecast,
    FxForecastBundle,
    diebold_mariano,
    fit_arimax,
    fit_vecm,
    forecast_fx,
    naive_dm_pvalue,
    random_walk_forecast,
)
from packages.core.models.cv import PurgedWalkForwardCV
from packages.core.models.errors import (
    GarchConvergenceError,
    GarchNonStationaryError,
    InsufficientHistoryError,
    ModelError,
    ModelUnavailableError,
)
from packages.core.models.garch import (
    QUALITY_FLAG as GARCH_FALLBACK_FLAG,
)
from packages.core.models.garch import (
    GarchResult,
    compute_vol_features,
    fit_garch,
    forecast_with_params,
)
from packages.core.models.ranker import (
    FittedRanker,
    RankerPrediction,
    evaluate_rank_ic,
    summarize_rank_ics,
    train_ranker,
    walk_forward_ics,
)

__all__ = [
    "DMResult",
    "FittedRanker",
    "Forecast",
    "FxForecastBundle",
    "GARCH_FALLBACK_FLAG",
    "GarchConvergenceError",
    "GarchNonStationaryError",
    "GarchResult",
    "InsufficientHistoryError",
    "ModelError",
    "ModelUnavailableError",
    "PurgedWalkForwardCV",
    "RankerPrediction",
    "compute_vol_features",
    "diebold_mariano",
    "evaluate_rank_ic",
    "fit_arimax",
    "fit_garch",
    "fit_vecm",
    "forecast_fx",
    "forecast_with_params",
    "naive_dm_pvalue",
    "random_walk_forecast",
    "summarize_rank_ics",
    "train_ranker",
    "walk_forward_ics",
]
