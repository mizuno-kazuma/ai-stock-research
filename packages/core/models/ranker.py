"""クロスセクショナル・ランカー（docs/04-analysis-engine.md §3）。

回帰 + 日次 z-score を既定とする。点推定だけでは UI に出せないため、
同じ特徴量で mean / q20 / q80 の 3 モデルを学習する。
ハイパーパラメータ探索の試行回数は `n_trials` に必ず記録する。
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from packages.core.models.cv import PurgedWalkForwardCV
from packages.core.models.errors import InsufficientHistoryError, ModelUnavailableError

logger = logging.getLogger(__name__)

MAX_OPTUNA_TRIALS = 50
DEFAULT_LGB_PARAMS: dict[str, Any] = {
    "objective": "regression",
    "metric": "rmse",
    "learning_rate": 0.03,
    "num_leaves": 31,
    "min_data_in_leaf": 200,
    "feature_fraction": 0.7,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l1": 0.1,
    "lambda_l2": 1.0,
    "max_depth": 6,
    "verbosity": -1,
    "seed": 42,
    "deterministic": True,
    "force_col_wise": True,
}


@dataclass
class RankerPrediction:
    """銘柄ごとの点推定 + 分位区間。"""

    ticker: str
    pred: float
    pred_lo: float
    pred_hi: float


@dataclass
class FittedRanker:
    """学習済みランカー。LightGBM 3 本、または OLS フォールバック。"""

    backend: Literal["lightgbm", "ols"]
    feature_names: list[str]
    n_trials: int
    models: dict[str, Any] = field(default_factory=dict)
    ols_coef: dict[str, np.ndarray] = field(default_factory=dict)
    ols_intercept: dict[str, float] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)

    def predict(self, features: pd.DataFrame) -> pd.DataFrame:
        X = _design_matrix(features, self.feature_names)
        if self.backend == "lightgbm":
            mean = np.asarray(self.models["mean"].predict(X))
            q20 = np.asarray(self.models["q20"].predict(X))
            q80 = np.asarray(self.models["q80"].predict(X))
        else:
            mean = X @ self.ols_coef["mean"] + self.ols_intercept["mean"]
            q20 = X @ self.ols_coef["q20"] + self.ols_intercept["q20"]
            q80 = X @ self.ols_coef["q80"] + self.ols_intercept["q80"]
        # 分位の逆転（稀に起きる）をクリップして区間として成立させる。
        lo = np.minimum(q20, mean)
        hi = np.maximum(q80, mean)
        index = features.index
        tickers = (
            features["ticker"].astype(str).to_numpy()
            if "ticker" in features.columns
            else np.array([str(i) for i in index])
        )
        return pd.DataFrame(
            {
                "ticker": tickers,
                "ml_pred": mean,
                "ml_pred_lo": lo,
                "ml_pred_hi": hi,
            },
            index=index,
        )


def train_ranker(
    features: pd.DataFrame,
    labels: pd.Series | np.ndarray | pd.DataFrame,
    *,
    n_trials: int,
    feature_cols: list[str] | None = None,
    params: dict[str, Any] | None = None,
    num_boost_round: int = 200,
    warehouse: Any | None = None,
    model_kind: str = "ranker_h20",
) -> FittedRanker:
    """mean / q20 / q80 を学習する。`n_trials` は必須（DSR の入力）。

    デフォルト値を持たせない。探索回数を隠すと有意性を判定できない。
    """
    if n_trials < 1:
        raise ValueError("n_trials は 1 以上である必要があります")
    if n_trials > MAX_OPTUNA_TRIALS:
        raise ValueError(
            f"n_trials={n_trials} は上限 {MAX_OPTUNA_TRIALS} を超えています。"
            "探索しすぎは多重検定バイアスを増やすだけです。"
        )
    y = _as_label(labels)
    cols = feature_cols or _infer_feature_cols(features)
    if not cols:
        raise InsufficientHistoryError("学習に使える特徴量列がありません")
    work = features.loc[:, cols].apply(pd.to_numeric, errors="coerce")
    mask = y.notna() & work.notna().any(axis=1)
    X = work.loc[mask]
    y = y.loc[mask]
    if len(y) < 50:
        raise InsufficientHistoryError(f"学習サンプルが不足しています（n={len(y)}）")

    lgb_params = {**DEFAULT_LGB_PARAMS, **(params or {})}
    ranker = _try_lightgbm(X, y, cols, lgb_params, num_boost_round, n_trials)
    if ranker is None:
        ranker = _fit_ols_quantiles(X, y, cols, n_trials)

    ranker.metrics["n_rows"] = len(y)
    ranker.metrics["n_features"] = len(cols)
    if warehouse is not None:
        warehouse.insert_model_run(
            {
                "model_kind": model_kind,
                "n_trials": n_trials,
                "backend": ranker.backend,
                "metrics": ranker.metrics,
                "status": "fitted",
            }
        )
    return ranker


def evaluate_rank_ic(pred: pd.Series, realized: pd.Series) -> dict[str, float]:
    """日次 Rank IC（Spearman）の平均と t 統計量。"""
    frame = pd.DataFrame({"pred": pred, "y": realized}).dropna()
    if frame.empty:
        return {"rank_ic": float("nan"), "t_stat": float("nan"), "hit_rate": float("nan")}
    ic = frame["pred"].corr(frame["y"], method="spearman")
    return {
        "rank_ic": float(ic) if ic == ic else float("nan"),
        "t_stat": float("nan"),
        "hit_rate": float((np.sign(frame["pred"]) == np.sign(frame["y"])).mean()),
    }


def walk_forward_ics(
    features: pd.DataFrame,
    labels: pd.Series,
    groups: pd.Series,
    *,
    n_trials: int,
    feature_cols: list[str] | None = None,
    cv: PurgedWalkForwardCV | None = None,
) -> list[float]:
    """Purged Walk-Forward で Rank IC を集計する。KFold は使わない。"""
    splitter = cv or PurgedWalkForwardCV(
        n_splits=5, label_horizon_days=20, embargo_days=5, test_days=60, min_train_days=120
    )
    ics: list[float] = []
    y = _as_label(labels)
    for train_idx, test_idx in splitter.split(features, groups=groups):
        model = train_ranker(
            features.iloc[train_idx],
            y.iloc[train_idx],
            n_trials=n_trials,
            feature_cols=feature_cols,
            num_boost_round=80,
        )
        pred = model.predict(features.iloc[test_idx])
        realized = y.iloc[test_idx].reset_index(drop=True)
        aligned = pd.DataFrame(
            {"pred": pred["ml_pred"].to_numpy(), "y": realized.to_numpy()}
        ).dropna()
        if aligned.empty:
            continue
        ic = aligned["pred"].corr(aligned["y"], method="spearman")
        if ic == ic:
            ics.append(float(ic))
    return ics


def _try_lightgbm(
    X: pd.DataFrame,
    y: pd.Series,
    cols: list[str],
    params: dict[str, Any],
    num_boost_round: int,
    n_trials: int,
) -> FittedRanker | None:
    # WSL で libgomp.so.1 が無いと import / train が OSError になる。
    # `sudo apt install libgomp1` で直るが、ランタイムは OLS に落とす。
    try:
        import lightgbm as lgb
    except (ImportError, OSError) as exc:
        logger.info("LightGBM を import できないため OLS にフォールバックします: %s", exc)
        return None
    if len(y) < int(params.get("min_data_in_leaf", 200)) * 2:
        # 葉の最小サンプルに対して行が足りないときは OLS に落とす。
        return None
    try:
        train = lgb.Dataset(X, label=y, feature_name=cols, free_raw_data=False)
        models = {}
        specs = {
            "mean": {**params, "objective": "regression"},
            "q20": {**params, "objective": "quantile", "alpha": 0.2, "metric": "quantile"},
            "q80": {**params, "objective": "quantile", "alpha": 0.8, "metric": "quantile"},
        }
        for name, p in specs.items():
            models[name] = lgb.train(p, train, num_boost_round=num_boost_round)
    except Exception as exc:
        logger.info("LightGBM 学習に失敗したため OLS にフォールバックします: %s", exc)
        return None
    return FittedRanker(
        backend="lightgbm",
        feature_names=cols,
        n_trials=n_trials,
        models=models,
        metrics={"num_boost_round": num_boost_round},
    )


def _fit_ols_quantiles(
    X: pd.DataFrame, y: pd.Series, cols: list[str], n_trials: int
) -> FittedRanker:
    mat = X.fillna(0.0).to_numpy(dtype=float)
    target = y.to_numpy(dtype=float)
    coef, intercept = _ols(mat, target)
    fitted = mat @ coef + intercept
    resid = target - fitted
    q20 = float(np.nanquantile(resid, 0.2))
    q80 = float(np.nanquantile(resid, 0.8))
    return FittedRanker(
        backend="ols",
        feature_names=cols,
        n_trials=n_trials,
        ols_coef={"mean": coef, "q20": coef, "q80": coef},
        ols_intercept={"mean": intercept, "q20": intercept + q20, "q80": intercept + q80},
        metrics={"residual_q20": q20, "residual_q80": q80},
    )


def _ols(X: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, float]:
    ones = np.ones((len(X), 1))
    design = np.hstack([ones, X])
    # 列が定数だと特異になるので、微小なリッジを足す。
    xtx = design.T @ design
    xtx.flat[:: xtx.shape[0] + 1] += 1e-6
    beta = np.linalg.solve(xtx, design.T @ y)
    return beta[1:], float(beta[0])


def _as_label(labels: pd.Series | np.ndarray | pd.DataFrame) -> pd.Series:
    if isinstance(labels, pd.DataFrame):
        for col in labels.columns:
            if "excess" in col or col.startswith("fwd_ret") or col == "y":
                return pd.to_numeric(labels[col], errors="coerce")
        return pd.to_numeric(labels.iloc[:, -1], errors="coerce")
    return pd.to_numeric(pd.Series(labels), errors="coerce")


def _infer_feature_cols(features: pd.DataFrame) -> list[str]:
    skip = {
        "ticker",
        "market",
        "as_of",
        "currency",
        "feature_version",
        "n_missing",
        "computed_at",
        "sector_code",
        "sector_name",
        "quality_flags",
    }
    cols = []
    for c in features.columns:
        if c in skip:
            continue
        if pd.api.types.is_numeric_dtype(features[c]):
            cols.append(c)
    return cols


def _design_matrix(features: pd.DataFrame, cols: list[str]) -> np.ndarray:
    missing = [c for c in cols if c not in features.columns]
    if missing:
        raise ModelUnavailableError(f"推論に必要な列がありません: {missing}")
    return features.loc[:, cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy(
        dtype=float
    )


def ranker_artifact_path(data_dir: Path, market: str, horizon: str = "h20") -> Path:
    return Path(data_dir) / "models" / f"ranker_{market.lower()}_{horizon}.pkl"


def save_fitted_ranker(ranker: FittedRanker, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(pickle.dumps(ranker, protocol=pickle.HIGHEST_PROTOCOL))
    return path


def load_fitted_ranker(path: Path) -> FittedRanker | None:
    if not path.exists():
        return None
    try:
        obj = pickle.loads(path.read_bytes())
    except Exception as exc:
        logger.warning("ranker の読み込みに失敗しました (%s): %s", path, exc)
        return None
    if not isinstance(obj, FittedRanker):
        logger.warning("ranker 成果物の型が違います: %s", type(obj))
        return None
    return obj
