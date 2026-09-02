"""個別株のみに絞る `UniverseFilter.common_stock_only`（docs/05-scoring-screening.md §7.1a）。"""

from __future__ import annotations

import pandas as pd

from packages.core.factors.screening import UniverseFilter


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"ticker": "7203", "product_category": "011"},  # 個別株
            {"ticker": "15600", "product_category": "014"},  # ETF
            {"ticker": "8987", "product_category": "013"},  # REIT
            {"ticker": "9999", "product_category": None},  # 未収集（除外しない）
        ]
    )


def test_common_stock_only_excludes_etf_and_reit_by_default() -> None:
    filt = UniverseFilter(market="JP")
    mask = filt.apply(_frame())
    passed = set(_frame().loc[mask, "ticker"])
    assert passed == {"7203", "9999"}


def test_common_stock_only_false_keeps_everything() -> None:
    filt = UniverseFilter(market="JP", common_stock_only=False)
    mask = filt.apply(_frame())
    assert mask.all()


def test_apply_is_noop_without_product_category_column() -> None:
    frame = pd.DataFrame([{"ticker": "7203"}, {"ticker": "15600"}])
    filt = UniverseFilter(market="JP")
    mask = filt.apply(frame)
    assert mask.all()


def test_from_config_defaults_common_stock_only_true() -> None:
    filt = UniverseFilter.from_config("JP")
    assert filt.common_stock_only is True
