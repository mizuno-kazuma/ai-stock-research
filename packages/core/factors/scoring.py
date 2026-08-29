"""スコアリング（docs/05-scoring-screening.md §2-§6）。

`features_daily` → winsorize → セクター中立化 z-score → グループ集約 →
重み付き合成 → `quant_score` → `total_score`。

内部の計算・順位付けには正規化前の `composite` を使う。`quant_score`（0-100）は
表示のためのクリップ済みの値であり、クリップにより情報が失われる。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from packages.core.factors.factor_config import (
    MIN_VALID_GROUPS,
    MIN_VALID_MEMBER_RATIO,
    FactorConfig,
    load_factor_config,
)
from packages.core.factors.transforms import (
    Z_CLIP,
    robust_zscore,
    sector_neutral_zscore,
    winsorize_frame,
)

#: `composite` を 0-100 に写すときのスケール。±2.5 で振り切れる。
COMPOSITE_SCALE = 2.5
#: 定性オーバーレイの最大調整幅（点）。
QUAL_ADJUSTMENT_CAP = 12.0

GROUP_Z_COLUMNS = (
    "value_z",
    "momentum_z",
    "quality_z",
    "growth_z",
    "lowvol_z",
    "revision_z",
)


def compute_group_z(
    features: pd.DataFrame,
    config: FactorConfig | None = None,
    *,
    sector_col: str = "sector_code",
    already_winsorized: bool = False,
) -> pd.DataFrame:
    """ファクターグループごとの z-score。

    グループ内の集約は「メンバーの z-score の重み付き平均を取り、再度 z-score 化」。
    欠損メンバーは重みを再正規化して除外するが、有効メンバーが半分未満のグループは
    `NULL` にする（残った1指標でグループを代表させない）。
    """
    cfg = config or load_factor_config()
    if features.empty:
        return pd.DataFrame(columns=[f"{g}_z" for g in cfg.group_names])

    work = features.copy()
    if not already_winsorized:
        cols = [c for c in cfg.features_used() if c in work.columns]
        work = winsorize_frame(
            work, cols, lower=cfg.winsorize["lower"], upper=cfg.winsorize["upper"]
        )

    out = pd.DataFrame(index=work.index)
    for group, members in cfg.factor_groups.items():
        weighted_sum = pd.Series(0.0, index=work.index)
        weight_total = pd.Series(0.0, index=work.index)
        valid_count = pd.Series(0, index=work.index)
        for member in members:
            if member.feature not in work.columns:
                continue
            z = sector_neutral_zscore(
                work,
                member.feature,
                sector_col=sector_col,
                min_sector_size=cfg.min_sector_size,
            )
            present = z.notna()
            weighted_sum = weighted_sum.add(
                (member.sign * member.weight * z).fillna(0.0), fill_value=0.0
            )
            weight_total = weight_total.add(
                pd.Series(member.weight, index=work.index).where(present, 0.0),
                fill_value=0.0,
            )
            valid_count = valid_count.add(present.astype(int), fill_value=0)
        normalized = weighted_sum / weight_total.replace(0.0, np.nan)
        required = max(1, int(np.ceil(len(members) * MIN_VALID_MEMBER_RATIO)))
        normalized = normalized.where(valid_count >= required)
        out[f"{group}_z"] = robust_zscore(normalized, clip=Z_CLIP)
    return out


def compute_quant_score(
    group_z: pd.DataFrame,
    *,
    market: str,
    horizon: str = "H20",
    config: FactorConfig | None = None,
    weights: dict[str, float] | None = None,
) -> pd.DataFrame:
    """重み付き合成と 0-100 正規化。

    欠損グループがある銘柄では有効グループの重みを再正規化する。ただし有効グループ
    が3つ未満の銘柄はスコアリング対象外（`NULL`）とする。
    """
    cfg = config or load_factor_config()
    group_weights = weights or cfg.weights_for(market, horizon)
    if group_z.empty:
        return pd.DataFrame(
            columns=["composite", "quant_score", "quant_rank", "quant_percentile", "n_valid_groups"]
        )

    weighted = pd.Series(0.0, index=group_z.index)
    weight_total = pd.Series(0.0, index=group_z.index)
    valid_groups = pd.Series(0, index=group_z.index)
    for group, weight in group_weights.items():
        col = f"{group}_z"
        if col not in group_z.columns:
            continue
        z = pd.to_numeric(group_z[col], errors="coerce")
        present = z.notna()
        weighted = weighted.add((weight * z).fillna(0.0), fill_value=0.0)
        weight_total = weight_total.add(
            pd.Series(weight, index=group_z.index).where(present, 0.0), fill_value=0.0
        )
        valid_groups = valid_groups.add(present.astype(int), fill_value=0)

    composite = (weighted / weight_total.replace(0.0, np.nan)).where(
        valid_groups >= MIN_VALID_GROUPS
    )
    out = pd.DataFrame(index=group_z.index)
    out["composite"] = composite
    out["quant_score"] = 50.0 + 50.0 * np.clip(composite / COMPOSITE_SCALE, -1.0, 1.0)
    out["quant_rank"] = composite.rank(ascending=False, method="min").astype("Int64")
    out["quant_percentile"] = composite.rank(pct=True)
    out["n_valid_groups"] = valid_groups.astype(int)
    return out


def total_score(
    quant_score: pd.Series | float,
    qual_score: pd.Series | float | None,
    qual_confidence: pd.Series | float | None = None,
) -> pd.Series | float:
    """定性スコアは定量スコアへの調整として作用する（置き換えではない）。

    調整幅を ±12点に限定するのは、LLM の定性判断が定量スコアを覆すことを避けるため。
    LLM は説明が上手いが、それは正しさとは別である。

    `qual_score` が `NULL` でもスコアが成立するので、LLM のコストキャップに達した日
    でも機能する（機能縮退）。
    """
    if isinstance(quant_score, pd.Series):
        quant = pd.to_numeric(quant_score, errors="coerce")
        qual = (
            pd.Series(0.0, index=quant.index)
            if qual_score is None
            else pd.to_numeric(pd.Series(qual_score, index=quant.index), errors="coerce")
        )
        confidence = (
            pd.Series(0.5, index=quant.index)
            if qual_confidence is None
            else pd.to_numeric(
                pd.Series(qual_confidence, index=quant.index), errors="coerce"
            ).fillna(0.5)
        )
        adjustment = (QUAL_ADJUSTMENT_CAP * qual * confidence).fillna(0.0)
        return (quant + adjustment).clip(0.0, 100.0)
    if qual_score is None or (isinstance(qual_score, float) and np.isnan(qual_score)):
        return float(quant_score)
    adjustment = QUAL_ADJUSTMENT_CAP * float(qual_score) * float(qual_confidence or 0.5)
    return float(np.clip(float(quant_score) + adjustment, 0.0, 100.0))


def score_cross_section(
    features: pd.DataFrame,
    *,
    market: str,
    horizon: str = "H20",
    config: FactorConfig | None = None,
    weights: dict[str, float] | None = None,
    qual_scores: pd.DataFrame | None = None,
    ml_predictions: pd.DataFrame | None = None,
    weight_set_id: str = "default",
) -> pd.DataFrame:
    """1日分の断面をスコアリングして `scores_daily` 相当の行を返す。"""
    cfg = config or load_factor_config()
    if features.empty:
        return pd.DataFrame()
    work = features.copy()
    if "ticker" in work.columns:
        work = work.set_index("ticker")
    group_z = compute_group_z(work, cfg)
    scores = compute_quant_score(
        group_z, market=market, horizon=horizon, config=cfg, weights=weights
    )
    out = pd.concat([group_z, scores], axis=1)
    out.insert(0, "market", market)
    if "as_of" in work.columns:
        out.insert(1, "as_of", work["as_of"])
    out["weight_set_id"] = weight_set_id
    if "feature_version" in work.columns:
        out["feature_version"] = work["feature_version"]
    else:
        from packages.core.factors.pipeline import FEATURE_VERSION

        out["feature_version"] = FEATURE_VERSION

    if ml_predictions is not None and not ml_predictions.empty:
        for col in ml_predictions.columns:
            out[col] = ml_predictions[col].reindex(out.index)

    if qual_scores is not None and not qual_scores.empty:
        out["qual_score"] = pd.to_numeric(
            qual_scores.get("qual_score"), errors="coerce"
        ).reindex(out.index)
        out["qual_confidence"] = pd.to_numeric(
            qual_scores.get("qual_confidence"), errors="coerce"
        ).reindex(out.index)
    else:
        out["qual_score"] = np.nan
        out["qual_confidence"] = np.nan

    out["total_score"] = total_score(
        out["quant_score"], out["qual_score"], out["qual_confidence"]
    )
    return out.reset_index()


def is_candidate(row: pd.Series) -> bool:
    """推奨候補の条件（docs §5）。

    `quant_score` と `ml_pred` の両方が上位であることを条件にする。前者は
    ルールベースで説明可能だが最適化されていない。後者は最適化されているが説明が
    難しい。両者が一致する銘柄は片方だけで選ぶより頑健である。
    """
    percentile = row.get("quant_percentile")
    pred = row.get("ml_pred_h20")
    pred_lo = row.get("ml_pred_h20_lo")
    if percentile is None or pd.isna(percentile) or percentile < 0.85:
        return False
    if pred is None or pd.isna(pred) or pred <= 0:
        return False
    if pred_lo is None or pd.isna(pred_lo) or pred_lo <= -0.05:
        return False
    return True


def candidate_mask(scores: pd.DataFrame) -> pd.Series:
    if scores.empty:
        return pd.Series(dtype=bool)
    return scores.apply(is_candidate, axis=1)
