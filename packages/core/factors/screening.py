"""ユニバースフィルタ・reason codes・action 判定（docs/05-scoring-screening.md §7, §9）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from packages.core.factors.factor_config import FactorConfig, load_factor_config
from packages.core.factors.registry import MAX_MISSING_FEATURES

#: docs §7.4。良い理由だけを並べないため、`DATA_STALE` と `MODEL_LOW_CONFIDENCE` の
#: ようなネガティブな情報も reason code として明示する。
REASON_CODES: dict[str, str] = {
    "VAL_CHEAP_VS_SECTOR": "セクター内で割安",
    "VAL_CHEAP_VS_HISTORY": "自社の過去水準比で割安",
    "MOM_STRONG_12M": "12ヶ月モメンタムが強い",
    "MOM_NEAR_52W_HIGH": "52週高値圏",
    "MOM_ABOVE_MA200": "200日線上",
    "QLT_HIGH_ROIC": "高いROIC",
    "QLT_LOW_LEVERAGE": "低レバレッジ",
    "QLT_CLEAN_ACCRUALS": "利益の質が良い",
    "GRW_ACCELERATING": "成長が加速",
    "REV_UP_GUIDANCE": "会社予想の上方修正",
    "REV_DOWN_GUIDANCE": "会社予想の下方修正",
    "VOL_LOW_REGIME": "低ボラ",
    "FX_TAILWIND": "為替が追い風",
    "FX_HEADWIND": "為替が逆風",
    "LLM_POSITIVE_GUIDANCE": "開示文書のトーンが前向き",
    "LLM_NEW_RISK_DISCLOSED": "新規リスクの開示",
    "EVENT_EARNINGS_SOON": "決算発表が近い",
    "DATA_STALE": "データが古い",
    "MODEL_LOW_CONFIDENCE": "モデルの直近成績が悪い",
    "RANK_FILL": "定量順位による件数補充",
}

CONVICTION_LEVELS = ("low", "medium", "high")
#: 母数がこれ未満なら `conviction` を low に強制する（docs §7.7）。
MIN_PRIOR_SAMPLES = 20
#: 高ボラ銘柄の閾値。年率実現ボラ。
HIGH_VOL_THRESHOLD = 0.60
#: 鮮度がこの営業日数以上遅れていたら `DATA_STALE`。
STALE_BUSINESS_DAYS = 3
EARNINGS_SOON_DAYS = 5

#: J-Quants 商品区分（`ProductCategory`）。個別株（内国株券）以外は ETF・REIT・
#: 優先出資証券・外国株の預託証券など（docs/03-data-model.md §2.1a）。
COMMON_STOCK_PRODUCT_CATEGORY = "011"


@dataclass(frozen=True)
class UniverseFilter:
    """バックテストとスクリーニングで共通に使うユニバース定義。"""

    market: str
    min_adv_20d: float | None = None
    min_market_cap: float | None = None
    exclude_sectors: tuple[str, ...] = ()
    exclude_recently_listed_days: int = 250
    max_price: float | None = None
    require_features_complete: bool = True
    max_missing: int = MAX_MISSING_FEATURES
    #: ETF・REIT・優先出資証券などを除外し、個別株のみ残す（docs/05 §7.1a）。
    #: `product_category` 列が無い（または `NULL` の）行は除外しない。
    common_stock_only: bool = True

    @classmethod
    def from_config(cls, market: str, config: FactorConfig | None = None) -> UniverseFilter:
        cfg = config or load_factor_config()
        raw: dict[str, Any] = dict(cfg.universe_filter.get(market, {}))
        return cls(
            market=market,
            min_adv_20d=raw.get("min_adv_20d"),
            min_market_cap=raw.get("min_market_cap"),
            exclude_sectors=tuple(raw.get("exclude_sectors") or ()),
            exclude_recently_listed_days=int(raw.get("exclude_recently_listed_days", 250)),
            max_price=raw.get("max_price"),
            require_features_complete=bool(raw.get("require_features_complete", True)),
            common_stock_only=bool(raw.get("common_stock_only", True)),
        )

    def apply(
        self,
        features: pd.DataFrame,
        *,
        as_of: date | None = None,
        listing_dates: pd.Series | None = None,
    ) -> pd.Series:
        """通過フラグを返す。除外理由の把握のため boolean Series で返す。"""
        if features.empty:
            return pd.Series(dtype=bool)
        mask = pd.Series(True, index=features.index)
        if self.min_adv_20d is not None and "adv_20d" in features.columns:
            adv = pd.to_numeric(features["adv_20d"], errors="coerce")
            mask &= adv.notna() & (adv >= self.min_adv_20d)
        if self.min_market_cap is not None and "market_cap" in features.columns:
            cap = pd.to_numeric(features["market_cap"], errors="coerce")
            mask &= cap.notna() & (cap >= self.min_market_cap)
        if self.exclude_sectors and "sector_code" in features.columns:
            mask &= ~features["sector_code"].astype(str).isin(self.exclude_sectors)
        if self.max_price is not None and "close" in features.columns:
            mask &= pd.to_numeric(features["close"], errors="coerce") <= self.max_price
        if self.common_stock_only and "product_category" in features.columns:
            category = features["product_category"].astype("string")
            # NULL（銘柄マスタ未収集・対象外市場）は除外しない。データ欠損で
            # ユニバースが全滅しないようにする（docs/05-scoring-screening.md §7.1a）。
            mask &= category.isna() | (category == COMMON_STOCK_PRODUCT_CATEGORY)
        if self.require_features_complete and "n_missing" in features.columns:
            mask &= pd.to_numeric(features["n_missing"], errors="coerce") <= self.max_missing
        if (
            self.exclude_recently_listed_days
            and listing_dates is not None
            and as_of is not None
        ):
            listed = pd.to_datetime(listing_dates.reindex(features.index), errors="coerce")
            age_days = (pd.Timestamp(as_of) - listed).dt.days
            # 上場日が不明な銘柄は除外しない（履歴長の判定は特徴量側の NULL で効く）。
            mask &= age_days.isna() | (age_days >= self.exclude_recently_listed_days)
        return mask


def assign_reason_codes(
    row: pd.Series,
    *,
    per_percentile_5y: float | None = None,
    vol_percentile: float | None = None,
    growth_accelerating: bool | None = None,
    fx_view_sign: int | None = None,
    guidance_tone: str | None = None,
    has_new_risk: bool = False,
    days_to_earnings: int | None = None,
    data_lag_business_days: int | None = None,
    model_ic_percentile: float | None = None,
) -> list[str]:
    """1銘柄分の reason codes。閾値は docs §7.4 の表そのまま。"""
    codes: list[str] = []

    def value_of(name: str) -> float:
        raw = row.get(name)
        return float(raw) if raw is not None and not pd.isna(raw) else float("nan")

    if value_of("value_z") >= 1.0:
        codes.append("VAL_CHEAP_VS_SECTOR")
    if per_percentile_5y is not None and per_percentile_5y <= 0.20:
        codes.append("VAL_CHEAP_VS_HISTORY")
    if value_of("momentum_z") >= 1.0:
        codes.append("MOM_STRONG_12M")
    if value_of("price_to_52w_high") >= 0.95:
        codes.append("MOM_NEAR_52W_HIGH")
    if value_of("dist_from_ma200") > 0:
        codes.append("MOM_ABOVE_MA200")
    if value_of("roic") >= 0.12 and value_of("quality_z") >= 0.5:
        codes.append("QLT_HIGH_ROIC")
    if value_of("debt_to_equity") <= 0.3:
        codes.append("QLT_LOW_LEVERAGE")
    if value_of("accruals_ratio") <= 0:
        codes.append("QLT_CLEAN_ACCRUALS")
    if growth_accelerating:
        codes.append("GRW_ACCELERATING")
    direction = row.get("forecast_revision_direction")
    if direction is not None and not pd.isna(direction):
        if int(direction) == 1:
            codes.append("REV_UP_GUIDANCE")
        elif int(direction) == -1:
            codes.append("REV_DOWN_GUIDANCE")
    if vol_percentile is not None and vol_percentile <= 0.30:
        codes.append("VOL_LOW_REGIME")
    fx_sensitivity = value_of("fx_sensitivity_60d")
    if fx_view_sign is not None and np.isfinite(fx_sensitivity) and fx_view_sign != 0:
        product = fx_sensitivity * fx_view_sign
        if product > 0:
            codes.append("FX_TAILWIND")
        elif product < 0:
            codes.append("FX_HEADWIND")
    if guidance_tone == "positive":
        codes.append("LLM_POSITIVE_GUIDANCE")
    if has_new_risk:
        codes.append("LLM_NEW_RISK_DISCLOSED")
    if days_to_earnings is not None and 0 <= days_to_earnings <= EARNINGS_SOON_DAYS:
        codes.append("EVENT_EARNINGS_SOON")
    if data_lag_business_days is not None and data_lag_business_days >= STALE_BUSINESS_DAYS:
        codes.append("DATA_STALE")
    if model_ic_percentile is not None and model_ic_percentile <= 0.10:
        codes.append("MODEL_LOW_CONFIDENCE")
    return codes


def determine_action(
    row: pd.Series, *, is_held: bool, in_watchlist: bool = False, invalidated: bool = False
) -> str | None:
    """docs §7.3。

    `watch` を「買い推奨」と呼ばないのは意図的である。本ツールは判断支援であり、
    買いを指示しない。
    """
    total = row.get("total_score")
    pred = row.get("ml_pred_h20")
    total = float(total) if total is not None and not pd.isna(total) else float("nan")
    pred = float(pred) if pred is not None and not pd.isna(pred) else float("nan")

    if is_held and invalidated:
        return "reduce"
    if is_held and np.isfinite(total) and total <= 35:
        return "reduce"
    if np.isfinite(total) and total >= 75 and np.isfinite(pred) and pred > 0.02:
        return "accumulate" if is_held else "watch"
    if not is_held and np.isfinite(total) and total <= 25 and in_watchlist:
        return "avoid"
    return None


def downgrade_conviction(level: str, steps: int = 1) -> str:
    index = CONVICTION_LEVELS.index(level) if level in CONVICTION_LEVELS else 0
    return CONVICTION_LEVELS[max(0, index - steps)]


def conviction_from_score(
    conviction_score: float,
    *,
    n_prior_samples: int | None,
    realized_vol_60d: float | None = None,
    high_vol_regime: bool = False,
) -> tuple[str, list[str]]:
    """確信度と、下げた理由のリストを返す。

    運用開始直後に高い確信度を出さないことが重要（docs §7.7）。実績が貯まっていない
    間は `low` 固定になる。
    """
    reasons: list[str] = []
    if conviction_score >= 0.70:
        level = "high"
    elif conviction_score >= 0.45:
        level = "medium"
    else:
        level = "low"
    if n_prior_samples is None or n_prior_samples < MIN_PRIOR_SAMPLES:
        if level != "low":
            reasons.append(f"類似条件の実績が {n_prior_samples or 0} 件（{MIN_PRIOR_SAMPLES} 件未満）")
        level = "low"
    if realized_vol_60d is not None and realized_vol_60d > HIGH_VOL_THRESHOLD:
        new_level = downgrade_conviction(level)
        if new_level != level:
            reasons.append(f"実現ボラが年率 {realized_vol_60d:.0%}（60% 超）")
        level = new_level
    if high_vol_regime:
        new_level = downgrade_conviction(level)
        if new_level != level:
            reasons.append("市場が高ボラレジーム")
        level = new_level
    return level, reasons


def _take_with_sector_cap(
    ordered: pd.DataFrame,
    *,
    limit: int,
    max_per_sector: int,
    sector_col: str,
    per_sector: dict[str, int] | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """順位済みの枠から、セクター上限を守りつつ `limit` 件まで取る。"""
    counts = dict(per_sector or {})
    if ordered.empty or limit <= 0:
        return ordered.iloc[0:0].copy(), counts
    selected: list[int] = []
    for position, (_, row) in enumerate(ordered.iterrows()):
        if len(selected) >= limit:
            break
        sector = str(row.get(sector_col, "__UNKNOWN__"))
        if counts.get(sector, 0) >= max_per_sector:
            continue
        counts[sector] = counts.get(sector, 0) + 1
        selected.append(position)
    return ordered.iloc[selected].copy(), counts


def apply_risk_constraints(
    candidates: pd.DataFrame,
    *,
    max_per_day: int = 10,
    max_per_sector: int = 3,
    sector_col: str = "sector_code",
    rank_col: str = "total_score",
) -> pd.DataFrame:
    """1日の推奨件数上限とセクター集中の制約（docs §7.2）。"""
    if candidates.empty:
        return candidates.copy()
    ordered = candidates.sort_values(rank_col, ascending=False, kind="mergesort")
    taken, _ = _take_with_sector_cap(
        ordered,
        limit=max_per_day,
        max_per_sector=max_per_sector,
        sector_col=sector_col,
    )
    return taken.reset_index(drop=True)


def select_recommendation_candidates(
    work: pd.DataFrame,
    *,
    max_per_day: int = 10,
    max_per_sector: int = 3,
    sector_col: str = "sector_code",
    rank_col: str = "total_score",
) -> pd.DataFrame:
    """厳格ゲートを優先し、不足分を定量順位で埋めて上限件数に近づける。

    旧実装は `is_candidate` 通過が0件のときだけ `total_score` 上位で埋めていた。
    通過が1件の日は補充が走らず、0件の日より情報量が少なかった。
    ゲート自体は緩めず、コア候補をセクター制約込みで先に取り、空き枠だけ埋める。
    補充分には `candidate_tier='fill'` を付け、後段で `RANK_FILL` と low 確信度を強制する。
    """
    if work.empty or max_per_day <= 0:
        out = work.iloc[0:0].copy()
        out["candidate_tier"] = pd.Series(dtype=str)
        return out

    ranked = work.sort_values(rank_col, ascending=False, kind="mergesort")
    from packages.core.factors.scoring import is_candidate

    strict_mask = ranked.apply(is_candidate, axis=1)
    core = ranked.loc[strict_mask].copy()
    fill_pool = ranked.loc[~strict_mask].copy()
    core["candidate_tier"] = "core"
    fill_pool["candidate_tier"] = "fill"

    taken_core, per_sector = _take_with_sector_cap(
        core,
        limit=max_per_day,
        max_per_sector=max_per_sector,
        sector_col=sector_col,
    )
    remaining = max_per_day - len(taken_core)
    taken_fill, _ = _take_with_sector_cap(
        fill_pool,
        limit=remaining,
        max_per_sector=max_per_sector,
        sector_col=sector_col,
        per_sector=per_sector,
    )
    combined = pd.concat([taken_core, taken_fill], ignore_index=True)
    return combined


@dataclass(frozen=True)
class HitRatePrior:
    """類似条件での過去的中率。母数を必ず併記する（docs §7.7）。"""

    hit_rate: float | None
    n_samples: int
    avg_excess: float | None
    is_fallback: bool = False

    @property
    def forces_low_conviction(self) -> bool:
        return self.n_samples < MIN_PRIOR_SAMPLES


def compute_hit_rate_prior(
    outcomes: pd.DataFrame,
    *,
    market: str,
    horizon: str,
    reason_codes: list[str],
    as_of: date,
    min_overlap: int = 2,
) -> HitRatePrior:
    """`recommendation_outcomes` から類似条件の的中率を求める。

    `r.as_of < as_of` を必須にする（未来の実績を使わない）。運用初期は空になるので
    `hit_rate = None` を返し、UI 側で「実績データの蓄積中」を表示させる。
    """
    if outcomes.empty:
        return HitRatePrior(hit_rate=None, n_samples=0, avg_excess=None)
    work = outcomes.copy()
    work["as_of"] = pd.to_datetime(work["as_of"], errors="coerce").dt.date
    work = work.loc[
        (work.get("market") == market)
        & (work.get("horizon") == horizon)
        & work["as_of"].notna()
        & (work["as_of"] < as_of)
    ]
    if work.empty:
        return HitRatePrior(hit_rate=None, n_samples=0, avg_excess=None)

    target = set(reason_codes)
    overlap = work["reason_codes"].map(
        lambda codes: len(target & set(codes or [])) if codes is not None else 0
    )
    similar = work.loc[overlap >= min_overlap]
    if len(similar) < MIN_PRIOR_SAMPLES:
        # 親カテゴリ（市場全体）にフォールバックする。
        fallback = work
        if fallback.empty:
            return HitRatePrior(hit_rate=None, n_samples=0, avg_excess=None)
        return HitRatePrior(
            hit_rate=float(pd.to_numeric(fallback["is_hit"], errors="coerce").mean()),
            n_samples=int(len(similar)),
            avg_excess=float(pd.to_numeric(fallback["excess_return"], errors="coerce").mean()),
            is_fallback=True,
        )
    return HitRatePrior(
        hit_rate=float(pd.to_numeric(similar["is_hit"], errors="coerce").mean()),
        n_samples=int(len(similar)),
        avg_excess=float(pd.to_numeric(similar["excess_return"], errors="coerce").mean()),
    )


SCREENER_PRESETS: dict[str, dict[str, Any]] = {
    "value_quality": {"value_z": (1.0, None), "quality_z": (0.5, None), "roic": (0.10, None)},
    "upward_revision_momentum": {
        "forecast_revision_direction": (1, 1),
        "momentum_z": (0.5, None),
    },
    "weak_yen_beneficiary": {"fx_sensitivity_60d": (0.3, None)},
    "strong_yen_beneficiary": {"fx_sensitivity_60d": (None, -0.3)},
    "low_vol_dividend": {"lowvol_z": (0.5, None), "dividend_yield": (0.03, None)},
    "high_growth": {"revenue_growth_yoy": (0.15, None), "eps_growth_yoy": (0.15, None)},
    # 警戒側のプリセットを用意することが、スクリーナーを「買い候補を探す道具」から
    # 「検討材料を集める道具」に変える（docs §9.2）。
    "value_trap_warning": {"value_z": (1.5, None), "quality_z": (None, -0.5)},
}

MAX_SCREENER_ROWS = 500


def apply_preset(scores: pd.DataFrame, preset: str) -> pd.DataFrame:
    if preset not in SCREENER_PRESETS:
        raise KeyError(f"unknown preset {preset!r}: {sorted(SCREENER_PRESETS)}")
    if scores.empty:
        return scores.copy()
    mask = pd.Series(True, index=scores.index)
    for col, (low, high) in SCREENER_PRESETS[preset].items():
        if col not in scores.columns:
            # 条件に使う列が無い場合、条件を無視すると誤った結果を返すので空にする。
            return scores.iloc[0:0].copy()
        values = pd.to_numeric(scores[col], errors="coerce")
        mask &= values.notna()
        if low is not None:
            mask &= values >= low
        if high is not None:
            mask &= values <= high
    return scores.loc[mask].head(MAX_SCREENER_ROWS).reset_index(drop=True)
