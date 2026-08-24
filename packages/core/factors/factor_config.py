"""ファクター定義の読み込み。

正本は `packages/core/config/factors.yaml`（API 担当が作成）。まだ存在しない間も
動くように、docs/05-scoring-screening.md §3-§7 の値を既定値として持つ。

**符号の定義をここに一元化する。** コード中に符号反転を散らすと必ずどこかで
間違える（docs §2.3）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "factors.yaml"

DEFAULT_FACTOR_GROUPS: dict[str, list[dict[str, Any]]] = {
    "value": [
        {"feature": "earnings_yield", "sign": 1, "weight": 0.30},
        {"feature": "fcf_yield", "sign": 1, "weight": 0.25},
        {"feature": "pbr", "sign": -1, "weight": 0.20},
        {"feature": "ev_ebitda", "sign": -1, "weight": 0.15},
        {"feature": "dividend_yield", "sign": 1, "weight": 0.10},
    ],
    "momentum": [
        {"feature": "mom_12_1", "sign": 1, "weight": 0.45},
        {"feature": "mom_6_1", "sign": 1, "weight": 0.25},
        {"feature": "price_to_52w_high", "sign": 1, "weight": 0.20},
        {"feature": "dist_from_ma200", "sign": 1, "weight": 0.10},
    ],
    "quality": [
        {"feature": "roic", "sign": 1, "weight": 0.30},
        {"feature": "roe", "sign": 1, "weight": 0.25},
        {"feature": "operating_margin", "sign": 1, "weight": 0.20},
        {"feature": "accruals_ratio", "sign": -1, "weight": 0.15},
        {"feature": "debt_to_equity", "sign": -1, "weight": 0.10},
    ],
    "growth": [
        {"feature": "eps_growth_yoy", "sign": 1, "weight": 0.35},
        {"feature": "revenue_growth_yoy", "sign": 1, "weight": 0.35},
        {"feature": "revenue_cagr_3y", "sign": 1, "weight": 0.30},
    ],
    "lowvol": [
        {"feature": "realized_vol_60d", "sign": -1, "weight": 0.40},
        {"feature": "max_drawdown_252d", "sign": -1, "weight": 0.35},
        {"feature": "beta_market_252d", "sign": -1, "weight": 0.25},
    ],
    "revision": [
        {"feature": "forecast_revision_direction", "sign": 1, "weight": 0.60},
        {"feature": "forecast_revision_magnitude", "sign": 1, "weight": 0.40},
    ],
}

#: **この初期値は「妥当そうな値」であり、根拠のある最適値ではない**（docs §4.1）。
#: Evaluator が実績に基づいて更新し、`factor_weights` に新しい weight_set_id を記録する。
DEFAULT_GROUP_WEIGHTS: dict[str, dict[str, dict[str, float]]] = {
    "JP": {
        "H5": {
            "value": 0.15,
            "momentum": 0.30,
            "quality": 0.15,
            "growth": 0.10,
            "lowvol": 0.15,
            "revision": 0.15,
        },
        "H20": {
            "value": 0.25,
            "momentum": 0.20,
            "quality": 0.20,
            "growth": 0.15,
            "lowvol": 0.10,
            "revision": 0.10,
        },
    },
    "US": {
        "H5": {
            "value": 0.10,
            "momentum": 0.35,
            "quality": 0.20,
            "growth": 0.15,
            "lowvol": 0.15,
            "revision": 0.05,
        },
        "H20": {
            "value": 0.20,
            "momentum": 0.25,
            "quality": 0.25,
            "growth": 0.20,
            "lowvol": 0.05,
            "revision": 0.05,
        },
    },
}

DEFAULT_UNIVERSE_FILTER: dict[str, dict[str, Any]] = {
    "JP": {
        "min_adv_20d": 100_000_000,
        "min_market_cap": 30_000_000_000,
        "exclude_sectors": [],
        "exclude_recently_listed_days": 250,
        "max_price": None,
        "require_features_complete": True,
    },
    "US": {
        "min_adv_20d": 5_000_000,
        "min_market_cap": 1_000_000_000,
        "exclude_sectors": [],
        "exclude_otc": True,
        "exclude_recently_listed_days": 250,
        "require_features_complete": True,
    },
}

DEFAULT_WINSORIZE = {"lower": 0.01, "upper": 0.99}
DEFAULT_MIN_SECTOR_SIZE = 8
#: グループ内の有効メンバーがこの比率未満なら NULL（残った1指標で代表させない）。
MIN_VALID_MEMBER_RATIO = 0.5
#: 有効グループがこの数未満の銘柄はスコアリング対象外。
MIN_VALID_GROUPS = 3


@dataclass(frozen=True)
class FactorMember:
    feature: str
    sign: int
    weight: float


@dataclass(frozen=True)
class FactorConfig:
    factor_groups: dict[str, list[FactorMember]]
    group_weights: dict[str, dict[str, dict[str, float]]]
    universe_filter: dict[str, dict[str, Any]]
    winsorize: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WINSORIZE))
    min_sector_size: int = DEFAULT_MIN_SECTOR_SIZE
    source_path: Path | None = None

    @property
    def group_names(self) -> list[str]:
        return list(self.factor_groups)

    def weights_for(self, market: str, horizon: str) -> dict[str, float]:
        try:
            return dict(self.group_weights[market][horizon])
        except KeyError as exc:
            raise KeyError(
                f"group_weights missing for market={market!r} horizon={horizon!r}"
            ) from exc

    def features_used(self) -> list[str]:
        return [m.feature for members in self.factor_groups.values() for m in members]


def _coerce_groups(raw: dict[str, Any]) -> dict[str, list[FactorMember]]:
    groups: dict[str, list[FactorMember]] = {}
    for name, body in raw.items():
        members_raw = body.get("members", body) if isinstance(body, dict) else body
        members = [
            FactorMember(
                feature=str(m["feature"]),
                sign=int(m.get("sign", 1)),
                weight=float(m.get("weight", 1.0)),
            )
            for m in members_raw
        ]
        if not members:
            continue
        groups[str(name)] = members
    return groups


def validate_group_weights(weights: dict[str, dict[str, dict[str, float]]]) -> None:
    """合計が 1.0 でない場合は起動時にエラーにする（docs §4.3）。"""
    for market, horizons in weights.items():
        for horizon, values in horizons.items():
            total = sum(values.values())
            if abs(total - 1.0) > 1e-6:
                raise ValueError(
                    f"group_weights[{market}][{horizon}] sums to {total:.6f}, expected 1.0"
                )


def load_factor_config(path: Path | None = None) -> FactorConfig:
    """`factors.yaml` を読む。無ければ仕様書由来の既定値を使う。"""
    target = path or DEFAULT_CONFIG_PATH
    raw: dict[str, Any] = {}
    if target.exists():
        import yaml

        raw = yaml.safe_load(target.read_text(encoding="utf-8")) or {}

    groups = (
        _coerce_groups(raw["factor_groups"])
        if raw.get("factor_groups")
        else _coerce_groups(DEFAULT_FACTOR_GROUPS)
    )
    group_weights = raw.get("group_weights") or DEFAULT_GROUP_WEIGHTS
    validate_group_weights(group_weights)
    return FactorConfig(
        factor_groups=groups,
        group_weights={
            market: {h: dict(v) for h, v in horizons.items()}
            for market, horizons in group_weights.items()
        },
        universe_filter=raw.get("universe_filter") or DEFAULT_UNIVERSE_FILTER,
        winsorize=raw.get("winsorize") or dict(DEFAULT_WINSORIZE),
        min_sector_size=int(raw.get("min_sector_size", DEFAULT_MIN_SECTOR_SIZE)),
        source_path=target if target.exists() else None,
    )
