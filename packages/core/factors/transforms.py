"""断面変換（winsorize / z-score / セクター中立化）。

docs/05-scoring-screening.md §2 に対応する。平均・標準偏差ではなく中央値・MAD を
使うのは、金融データの分布が裾が重く、平均と標準偏差が外れ値に引っ張られるため。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

Z_CLIP = 3.0
DEFAULT_MIN_SECTOR_SIZE = 8


def mad_std(s: pd.Series) -> float:
    """MAD から標準偏差相当量を推定する。1.4826 は正規分布での換算係数。"""
    values = pd.to_numeric(s, errors="coerce").dropna()
    if values.empty:
        return float("nan")
    return float(1.4826 * (values - values.median()).abs().median())


def _mad_std_transform(s: pd.Series) -> pd.Series:
    return pd.Series(mad_std(s), index=s.index, dtype="float64")


def winsorize(s: pd.Series, lower: float = 0.01, upper: float = 0.99) -> pd.Series:
    """分位点クリップ。

    除外ではなくクリップにするのは、外れ値銘柄を落とすとユニバースが日ごとに
    変わってしまうため。
    """
    values = pd.to_numeric(s, errors="coerce")
    if values.dropna().empty:
        return values
    lo, hi = values.quantile(lower), values.quantile(upper)
    return values.clip(lo, hi)


def winsorize_frame(
    df: pd.DataFrame,
    cols: list[str],
    *,
    group_cols: list[str] | None = None,
    lower: float = 0.01,
    upper: float = 0.99,
) -> pd.DataFrame:
    """各日・各市場内で分位点クリップする。"""
    out = df.copy()
    present = [c for c in cols if c in out.columns]
    if not present:
        return out
    if group_cols:
        groups = [c for c in group_cols if c in out.columns]
        if groups:
            for col in present:
                out[col] = out.groupby(groups, sort=False)[col].transform(
                    lambda s: winsorize(s, lower, upper)
                )
            return out
    for col in present:
        out[col] = winsorize(out[col], lower, upper)
    return out


def robust_zscore(s: pd.Series, *, clip: float = Z_CLIP) -> pd.Series:
    values = pd.to_numeric(s, errors="coerce")
    scale = mad_std(values)
    if not np.isfinite(scale) or scale == 0:
        # MAD が退化する（同値が過半）場合のみ標準偏差にフォールバックする。
        scale = float(values.std(ddof=0))
        if not np.isfinite(scale) or scale == 0:
            return pd.Series(np.nan, index=values.index, dtype="float64")
    return ((values - values.median()) / scale).clip(-clip, clip)


def sector_neutral_zscore(
    df: pd.DataFrame,
    col: str,
    *,
    sector_col: str = "sector_code",
    min_sector_size: int = DEFAULT_MIN_SECTOR_SIZE,
    clip: float = Z_CLIP,
) -> pd.Series:
    """同一 as_of・同一セクター内で z-score を取る。

    セクターの構成銘柄が `min_sector_size` 未満の場合は市場全体で計算する
    （小サンプルの z-score は不安定なため）。

    セクター中立化を行う理由: 業種によって PER や ROE の水準が構造的に違う。
    銀行と製薬の PER を直接比べても意味がない。
    """
    values = pd.to_numeric(df[col], errors="coerce")
    z_market = robust_zscore(values, clip=clip)
    if sector_col not in df.columns:
        return z_market
    sector = df[sector_col].fillna("__UNKNOWN__")
    grouped = values.groupby(sector)
    sizes = grouped.transform("count")
    center = grouped.transform("median")
    scale = grouped.transform(_mad_std_transform)
    with np.errstate(divide="ignore", invalid="ignore"):
        z_sector = ((values - center) / scale.replace(0.0, np.nan)).clip(-clip, clip)
    # MAD が退化する（同値が過半）とき、中央値上の点は 0、外れ値はクリップする。
    degenerate = scale.eq(0.0) & values.notna()
    z_sector = z_sector.where(~(degenerate & values.eq(center)), 0.0)
    signed = np.sign(values - center) * clip
    z_sector = z_sector.where(~(degenerate & ~values.eq(center)), signed)
    return z_sector.where(sizes >= min_sector_size, z_market)


def cross_sectional_zscore(
    df: pd.DataFrame,
    col: str,
    *,
    date_col: str = "as_of",
    sector_col: str = "sector_code",
    min_sector_size: int = DEFAULT_MIN_SECTOR_SIZE,
) -> pd.Series:
    """日付ごとにセクター中立 z-score を計算する。

    日付を跨いだ z-score は「未来の断面分布」を使うことになるためリークになる。
    必ず日付でグループ化する。
    """
    if df.empty:
        return pd.Series(dtype="float64")
    if date_col not in df.columns:
        return sector_neutral_zscore(
            df, col, sector_col=sector_col, min_sector_size=min_sector_size
        )
    parts: list[pd.Series] = []
    for _, chunk in df.groupby(date_col, sort=False):
        parts.append(
            sector_neutral_zscore(
                chunk, col, sector_col=sector_col, min_sector_size=min_sector_size
            )
        )
    return pd.concat(parts).reindex(df.index)


def cross_sectional_rank(s: pd.Series, *, pct: bool = True) -> pd.Series:
    values = pd.to_numeric(s, errors="coerce")
    return values.rank(pct=pct, ascending=True)


def sector_demean(
    df: pd.DataFrame, col: str, *, sector_col: str = "sector_code"
) -> pd.Series:
    """セクター中央値との差。`sector_relative_ret_20d` などに使う。"""
    values = pd.to_numeric(df[col], errors="coerce")
    if sector_col not in df.columns:
        return values - values.median()
    medians = values.groupby(df[sector_col].fillna("__UNKNOWN__")).transform("median")
    return values - medians
