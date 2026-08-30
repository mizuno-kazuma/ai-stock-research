"""T-STAT-04: セクター中立化は中央値と MAD を使う。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from packages.core.factors.transforms import sector_neutral_zscore


def test_sector_neutral_zscore_uses_median_and_mad() -> None:
    df = pd.DataFrame({"sector_code": ["A"] * 20, "per": [15.0] * 19 + [10000.0]})
    z = sector_neutral_zscore(df, "per")
    assert abs(float(z.iloc[:19].mean())) < 0.3


def test_small_sector_falls_back_to_market() -> None:
    per = [10.0, 11.0, 12.0] + list(np.linspace(20.0, 30.0, 50))
    df = pd.DataFrame({"sector_code": ["A"] * 3 + ["B"] * 50, "per": per})
    z = sector_neutral_zscore(df, "per", min_sector_size=8)
    assert not z.iloc[:3].isna().any()
