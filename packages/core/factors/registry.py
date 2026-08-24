"""特徴量レジストリ。

add-analysis-factor SKILL は「`as_of` 時点で何が入手可能か」を特徴量ごとに書き
下すことを要求する。その定義をコードの隣に置いて、レビューとリーク検証の基準に
する。ここに登録されていない列は `features_daily` に書き出さない。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Category = Literal[
    "return",
    "volatility",
    "technical",
    "liquidity",
    "valuation",
    "quality",
    "growth",
    "revision",
    "fx",
]


@dataclass(frozen=True)
class FactorSpec:
    """1 つの特徴量の定義。

    Attributes:
        name: `features_daily` の列名。
        category: 分類。
        as_of_source: `as_of` 時点で参照する情報源と、その入手可能性の根拠。
        min_history_days: これ未満の履歴では `NULL`。
        winsorize: 断面で分位点クリップするか（比率系は原則 True）。
        higher_is_better: z-score の符号。None は方向を持たない指標。
        notes: 実装上の注意。
    """

    name: str
    category: Category
    as_of_source: str
    min_history_days: int = 0
    winsorize: bool = False
    higher_is_better: bool | None = None
    notes: str = ""


_SPECS: tuple[FactorSpec, ...] = (
    # --- リターン・モメンタム（docs §1.2） -------------------------------
    FactorSpec("ret_1d", "return", "as_of 当日終値と前営業日終値", 2, True, None),
    FactorSpec("ret_5d", "return", "as_of 当日終値と5営業日前終値", 6, True, None),
    FactorSpec("ret_20d", "return", "as_of 当日終値と20営業日前終値", 21, True, None),
    FactorSpec("ret_60d", "return", "as_of 当日終値と60営業日前終値", 61, True, None),
    FactorSpec("ret_252d", "return", "as_of 当日終値と252営業日前終値", 253, True, None),
    FactorSpec(
        "mom_12_1",
        "return",
        "21営業日前と252営業日前の終値のみ（当日終値は使わない）",
        253,
        True,
        True,
        "直近1ヶ月を除外して短期反転効果を排除する",
    ),
    FactorSpec("mom_6_1", "return", "21営業日前と126営業日前の終値", 127, True, True),
    FactorSpec(
        "price_to_52w_high", "return", "過去252営業日の終値最大値と当日終値", 200, True, True
    ),
    FactorSpec("dist_from_ma200", "return", "過去200営業日の終値平均と当日終値", 200, True, True),
    FactorSpec(
        "sector_relative_ret_20d",
        "return",
        "同一 as_of の同セクター銘柄の ret_20d 中央値（同日断面のみ）",
        21,
        True,
        True,
        "断面計算は必ず同一日内で行う。日付を跨ぐとリーク",
    ),
    # --- ボラティリティ（docs §1.3） --------------------------------------
    FactorSpec("realized_vol_20d", "volatility", "過去20営業日の対数リターン", 21, True, False),
    FactorSpec("realized_vol_60d", "volatility", "過去60営業日の対数リターン", 61, True, False),
    FactorSpec("downside_dev_60d", "volatility", "過去60営業日の負のリターンのみ", 61, True, False),
    FactorSpec("max_drawdown_252d", "volatility", "過去252営業日の終値", 200, True, False),
    FactorSpec(
        "beta_market_252d",
        "volatility",
        "過去252営業日の銘柄リターンとベンチマークリターン",
        200,
        True,
        False,
        "ベンチマークが無い場合は NULL。等ウェイト平均で代用しない",
    ),
    FactorSpec("atr_14", "volatility", "過去14営業日の高値・低値・終値", 15, True, None),
    FactorSpec(
        "garch_vol_1d",
        "volatility",
        "前週推定の GARCH(1,1) パラメータ + as_of までのリターン",
        500,
        False,
        False,
        "収束しない場合は realized_vol にフォールバックし quality_flags に記録",
    ),
    FactorSpec("garch_vol_20d", "volatility", "同上（20営業日平均分散）", 500, False, False),
    # --- テクニカル（docs §1.4） -----------------------------------------
    FactorSpec("rsi_14", "technical", "過去14営業日の終値", 15, False, None),
    FactorSpec("macd", "technical", "EMA12 - EMA26（as_of 当日まで）", 35, True, None),
    FactorSpec("macd_signal", "technical", "EMA9(macd)", 35, True, None),
    FactorSpec("macd_hist", "technical", "macd - macd_signal", 35, True, None),
    FactorSpec("bb_pct_b_20", "technical", "過去20営業日の終値平均と標準偏差", 20, False, None),
    # --- 流動性（docs §1.5） ---------------------------------------------
    FactorSpec(
        "adv_20d",
        "liquidity",
        "過去20営業日の売買代金",
        20,
        False,
        None,
        "スコア構成要素ではなくユニバースフィルタとして使う",
    ),
    FactorSpec("turnover_ratio", "liquidity", "as_of 当日の売買代金と時価総額", 1, True, None),
    FactorSpec("amihud_illiq", "liquidity", "過去20営業日のリターンと売買代金", 20, True, False),
    # --- バリュエーション（docs §1.6） -----------------------------------
    FactorSpec(
        "per",
        "valuation",
        "filed_at <= as_of の財務から作った TTM 純利益 + 当日時価総額",
        0,
        True,
        None,
        "赤字は NULL。表示用のみ。ランキングには earnings_yield を使う",
    ),
    FactorSpec("per_forward", "valuation", "会社予想純利益（filed_at <= as_of）", 0, True, None),
    FactorSpec("pbr", "valuation", "直近開示の純資産 + 当日時価総額", 0, True, False),
    FactorSpec("psr", "valuation", "TTM 売上 + 当日時価総額", 0, True, False),
    FactorSpec("ev_ebitda", "valuation", "TTM EBITDA + 当日時価総額 + 直近開示の負債・現金", 0, True, False),
    FactorSpec("fcf_yield", "valuation", "TTM 営業CF - 設備投資 + 当日時価総額", 0, True, True),
    FactorSpec("dividend_yield", "valuation", "TTM 一株配当 + 当日終値", 0, True, True),
    FactorSpec(
        "earnings_yield",
        "valuation",
        "TTM 純利益 + 当日時価総額",
        0,
        True,
        True,
        "赤字が負値として自然に下位に落ちる",
    ),
    # --- クオリティ（docs §1.7） -----------------------------------------
    FactorSpec("roe", "quality", "TTM 純利益 + 過去4期の平均自己資本", 0, True, True),
    FactorSpec("roic", "quality", "TTM 営業利益 × (1 - 実効税率) + 投下資本", 0, True, True),
    FactorSpec("gross_margin", "quality", "TTM 売上と売上原価", 0, True, True),
    FactorSpec("operating_margin", "quality", "TTM 営業利益と売上", 0, True, True),
    FactorSpec("debt_to_equity", "quality", "直近開示の負債と純資産", 0, True, False),
    FactorSpec("interest_coverage", "quality", "TTM 営業利益と支払利息", 0, True, True),
    FactorSpec(
        "accruals_ratio",
        "quality",
        "TTM 純利益と営業CF + 直近開示の総資産",
        0,
        True,
        False,
        "利益の質。符号を反転してクオリティ因子に使う",
    ),
    # --- 成長・改定（docs §1.8） -----------------------------------------
    FactorSpec("revenue_growth_yoy", "growth", "TTM 売上と4期前 TTM 売上", 0, True, True),
    FactorSpec("eps_growth_yoy", "growth", "TTM EPS と4期前 TTM EPS", 0, True, True),
    FactorSpec("revenue_cagr_3y", "growth", "TTM 売上と12期前 TTM 売上", 0, True, True),
    FactorSpec(
        "forecast_revision_direction",
        "revision",
        "filed_at <= as_of の会社予想営業利益の最新2件",
        0,
        False,
        True,
        "日本株で特に有効。TDnet の guidance_revision でも代替可能",
    ),
    FactorSpec("forecast_revision_magnitude", "revision", "同上（比率）", 0, True, True),
    # --- 為替（docs §1.9） -----------------------------------------------
    FactorSpec(
        "fx_sensitivity_60d",
        "fx",
        "過去60営業日の銘柄リターンと USD/JPY リターン",
        61,
        True,
        None,
        "為替見通しと組み合わせて初めて方向が決まるので符号を持たない",
    ),
)

REGISTRY: dict[str, FactorSpec] = {spec.name: spec for spec in _SPECS}
FEATURE_COLUMNS: tuple[str, ...] = tuple(REGISTRY)
WINSORIZE_COLUMNS: tuple[str, ...] = tuple(
    name for name, spec in REGISTRY.items() if spec.winsorize
)
#: `n_missing > 15` でスコアリング対象外にする際の母数（docs §1.10）。
N_FEATURES_FOR_MISSING = len(FEATURE_COLUMNS)
MAX_MISSING_FEATURES = 15


def by_category(category: Category) -> list[FactorSpec]:
    return [spec for spec in REGISTRY.values() if spec.category == category]


def spec(name: str) -> FactorSpec:
    if name not in REGISTRY:
        raise KeyError(
            f"unregistered factor {name!r}. add a FactorSpec first "
            "(see .cursor/skills/add-analysis-factor/SKILL.md)"
        )
    return REGISTRY[name]
