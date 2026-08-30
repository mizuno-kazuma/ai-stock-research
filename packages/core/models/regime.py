"""市場レジーム検出（docs/04-analysis-engine.md §5）。

予測には使わない。高ボラ・高相関・モデル劣化・特徴量ドリフトを
注意喚起として返す。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

HIGH_VOL_PERCENTILE = 0.80
HIGH_CORR_THRESHOLD = 0.50
LOW_CORR_THRESHOLD = 0.25
IC_LOOKBACK_RECENT = 20
IC_LOOKBACK_YEAR = 252
IC_DEGRADE_QUANTILE = 0.10
KS_PVALUE = 0.01
KS_MIN_FEATURES = 3
CORR_WINDOW = 60
CORR_MAX_TICKERS = 40
VOL_WINDOW = 20
VOL_LOOKBACK = 252 * 5


@dataclass(frozen=True)
class VolRegimeResult:
    level: str
    percentile: float | None
    message_ja: str | None
    high_vol: bool = False


@dataclass(frozen=True)
class CorrRegimeResult:
    avg_pairwise_corr_60d: float | None
    level: str | None


@dataclass(frozen=True)
class ModelDegradationResult:
    rank_ic_20d: float | None
    rank_ic_percentile_1y: float | None
    degraded: bool
    message_ja: str | None = None


@dataclass(frozen=True)
class FeatureDriftResult:
    n_drifted: int
    drifted_features: list[str] = field(default_factory=list)
    retrain_recommended: bool = False
    message_ja: str | None = None


@dataclass(frozen=True)
class RegimeSnapshot:
    vol: VolRegimeResult
    correlation: CorrRegimeResult
    model: ModelDegradationResult
    drift: FeatureDriftResult


def _percentile_rank(history: pd.Series, current: float) -> float:
    hist = pd.to_numeric(history, errors="coerce").dropna()
    if hist.empty:
        return float("nan")
    return float((hist <= current).mean())


def vol_regime_from_levels(
    levels: pd.Series,
    *,
    window: int = VOL_WINDOW,
    lookback: int = VOL_LOOKBACK,
) -> VolRegimeResult:
    """価格水準から実現ボラの過去パーセンタイルを出す。

    GARCH 日次値が無い場合のフォールバック。仕様の「過去5年パーセンタイル /
    80超で確信度を1段下げる」に合わせる。
    """
    close = pd.to_numeric(levels, errors="coerce").dropna().sort_index()
    if len(close) < window + 5:
        return VolRegimeResult(
            level="unknown",
            percentile=None,
            message_ja="ボラティリティ判定に必要な履歴が不足しています",
            high_vol=False,
        )
    rets = close.pct_change()
    rv = rets.rolling(window, min_periods=window).std() * float(np.sqrt(252))
    hist = rv.dropna()
    if hist.empty:
        return VolRegimeResult(
            level="unknown", percentile=None, message_ja=None, high_vol=False
        )
    windowed = hist.iloc[-min(len(hist), lookback) :]
    current = float(windowed.iloc[-1])
    percentile = _percentile_rank(windowed, current)
    if not np.isfinite(percentile):
        return VolRegimeResult(
            level="unknown", percentile=None, message_ja=None, high_vol=False
        )
    high_vol = percentile >= HIGH_VOL_PERCENTILE
    if high_vol:
        level = "high"
        message = (
            f"ボラティリティは過去5年の{percentile:.0%}パーセンタイル。"
            "推奨の確信度を1段下げています"
        )
    elif percentile >= 0.60:
        level = "elevated"
        message = f"ボラティリティは過去5年の{percentile:.0%}パーセンタイルです"
    else:
        level = "normal"
        message = f"ボラティリティは過去5年の{percentile:.0%}パーセンタイル（中位圏）です"
    return VolRegimeResult(
        level=level,
        percentile=percentile,
        message_ja=message,
        high_vol=high_vol,
    )


def correlation_regime(
    close_panel: pd.DataFrame,
    *,
    window: int = CORR_WINDOW,
    max_tickers: int = CORR_MAX_TICKERS,
) -> CorrRegimeResult:
    """直近 window 営業日の銘柄間平均相関。"""
    if close_panel is None or close_panel.empty:
        return CorrRegimeResult(avg_pairwise_corr_60d=None, level=None)
    work = close_panel.copy()
    if "ticker" in work.columns and "close" in work.columns:
        date_col = "trade_date" if "trade_date" in work.columns else "as_of"
        if date_col not in work.columns:
            return CorrRegimeResult(avg_pairwise_corr_60d=None, level=None)
        work[date_col] = pd.to_datetime(work[date_col], errors="coerce")
        work["close"] = pd.to_numeric(work["close"], errors="coerce")
        counts = work.groupby("ticker")["close"].count()
        keep = list(counts.sort_values(ascending=False).head(max_tickers).index)
        work = work[work["ticker"].isin(keep)]
        wide = work.pivot_table(index=date_col, columns="ticker", values="close")
    else:
        wide = work.apply(pd.to_numeric, errors="coerce")
        if wide.shape[1] > max_tickers:
            wide = wide.iloc[:, :max_tickers]
    wide = wide.sort_index().iloc[-window:]
    if wide.shape[0] < 20 or wide.shape[1] < 3:
        return CorrRegimeResult(avg_pairwise_corr_60d=None, level=None)
    rets = wide.pct_change().dropna(how="all")
    corr = rets.corr()
    if corr.empty:
        return CorrRegimeResult(avg_pairwise_corr_60d=None, level=None)
    mask = np.triu(np.ones(corr.shape, dtype=bool), k=1)
    vals = corr.to_numpy()[mask]
    vals = vals[np.isfinite(vals)]
    if vals.size == 0:
        return CorrRegimeResult(avg_pairwise_corr_60d=None, level=None)
    avg = float(np.mean(vals))
    if avg >= HIGH_CORR_THRESHOLD:
        level = "high"
    elif avg <= LOW_CORR_THRESHOLD:
        level = "low"
    else:
        level = "normal"
    return CorrRegimeResult(avg_pairwise_corr_60d=avg, level=level)


def model_degradation(
    daily_ics: pd.Series,
    *,
    recent: int = IC_LOOKBACK_RECENT,
    year: int = IC_LOOKBACK_YEAR,
) -> ModelDegradationResult:
    """直近20日 Rank IC が過去1年の下位10%以下なら劣化。"""
    series = pd.to_numeric(daily_ics, errors="coerce").dropna().sort_index()
    if len(series) < recent:
        return ModelDegradationResult(
            rank_ic_20d=None,
            rank_ic_percentile_1y=None,
            degraded=False,
            message_ja="モデル劣化判定に必要な Rank IC 履歴が不足しています",
        )
    recent_ic = float(series.iloc[-recent:].mean())
    hist = series.iloc[-min(len(series), year) :]
    percentile = _percentile_rank(hist, recent_ic)
    degraded = bool(np.isfinite(percentile) and percentile <= IC_DEGRADE_QUANTILE)
    message = None
    if degraded:
        message = "モデルの直近パフォーマンスが劣化しています"
    return ModelDegradationResult(
        rank_ic_20d=recent_ic,
        rank_ic_percentile_1y=percentile if np.isfinite(percentile) else None,
        degraded=degraded,
        message_ja=message,
    )


def feature_drift_ks(
    train: pd.DataFrame,
    recent: pd.DataFrame,
    columns: list[str] | None = None,
    *,
    pvalue: float = KS_PVALUE,
) -> FeatureDriftResult:
    """学習期間 vs 直近の KS 検定。p < 0.01 が3列以上なら再学習を推奨。"""
    from scipy.stats import ks_2samp

    cols = columns or [
        c
        for c in train.columns
        if c in recent.columns and pd.api.types.is_numeric_dtype(train[c])
    ]
    drifted: list[str] = []
    for col in cols:
        a = pd.to_numeric(train[col], errors="coerce").dropna()
        b = pd.to_numeric(recent[col], errors="coerce").dropna()
        if len(a) < 20 or len(b) < 20:
            continue
        stat = ks_2samp(a.to_numpy(), b.to_numpy())
        if float(stat.pvalue) < pvalue:
            drifted.append(col)
    n = len(drifted)
    recommend = n >= KS_MIN_FEATURES
    message = None
    if recommend:
        message = f"特徴量ドリフトが {n} 列で検出されたため、モデル再学習を推奨します"
    return FeatureDriftResult(
        n_drifted=n,
        drifted_features=drifted,
        retrain_recommended=recommend,
        message_ja=message,
    )


def snapshot_from_prices(
    *,
    benchmark_levels: pd.Series | None,
    close_panel: pd.DataFrame | None = None,
    daily_ics: pd.Series | None = None,
    train_features: pd.DataFrame | None = None,
    recent_features: pd.DataFrame | None = None,
) -> RegimeSnapshot:
    vol = (
        vol_regime_from_levels(benchmark_levels)
        if benchmark_levels is not None
        else VolRegimeResult(level="unknown", percentile=None, message_ja=None)
    )
    corr = (
        correlation_regime(close_panel)
        if close_panel is not None
        else CorrRegimeResult(avg_pairwise_corr_60d=None, level=None)
    )
    model = (
        model_degradation(daily_ics)
        if daily_ics is not None
        else ModelDegradationResult(
            rank_ic_20d=None, rank_ic_percentile_1y=None, degraded=False
        )
    )
    drift = (
        feature_drift_ks(train_features, recent_features)
        if train_features is not None and recent_features is not None
        else FeatureDriftResult(n_drifted=0)
    )
    return RegimeSnapshot(vol=vol, correlation=corr, model=model, drift=drift)
