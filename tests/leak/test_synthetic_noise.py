"""T-LEAK-04: 合成ノイズから有意な Rank IC が出ないこと。"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from packages.core.factors.labels import make_label
from packages.core.factors.panel import PricePanel
from packages.core.factors.pipeline import build_pit_context, compute_features
from packages.core.models.cv import PurgedWalkForwardCV
from packages.core.models.ranker import train_ranker
from tests.factories import make_prices, make_securities


def test_pipeline_finds_no_signal_in_pure_noise() -> None:
    rng = np.random.default_rng(42)
    n_days, n_stocks = 280, 16
    tickers = [f"{1000 + i}" for i in range(n_stocks)]
    prices = make_prices(tickers, n_days=n_days, seed=42)
    # リターンを完全なノイズに差し替え（構造的ドリフトを消す）。
    shocks = rng.normal(0.0, 0.012, size=len(prices))
    prices = prices.copy()
    prices["adj_close"] = 1000.0 * np.exp(np.cumsum(shocks))
    prices["close"] = prices["adj_close"]
    prices["adj_open"] = prices["adj_close"] * 0.999
    prices["open"] = prices["adj_open"]
    securities = make_securities(tickers)
    dates = sorted(pd.to_datetime(prices["trade_date"]).dt.date.unique())
    # 計算コストを抑えるため 2 営業日おき。purge+embargo 後も学習日数が残るようにする。
    as_ofs = dates[80:-25:2]
    rows = []
    labels = []
    for as_of in as_ofs:
        ctx = build_pit_context(
            as_of=as_of, market="JP", prices=prices, securities=securities
        )
        feat = compute_features(ctx)
        if feat.empty:
            continue
        lab = make_label(prices, as_of, horizon=20)
        feat = feat.set_index("ticker")
        common = feat.index.intersection(lab.index)
        if common.empty:
            continue
        chunk = feat.loc[common].reset_index()
        chunk["as_of"] = as_of
        chunk["y"] = lab.loc[common].to_numpy()
        rows.append(chunk)
    panel = pd.concat(rows, ignore_index=True)
    feature_cols = [
        c
        for c in ("ret_5d", "ret_20d", "mom_12_1", "realized_vol_20d", "rsi_14")
        if c in panel.columns
    ]
    cv = PurgedWalkForwardCV(
        n_splits=3,
        label_horizon_days=20,
        embargo_days=5,
        test_days=10,
        min_train_days=20,
    )
    ics = []
    groups = panel["as_of"]
    for train_idx, test_idx in cv.split(panel, groups=groups):
        model = train_ranker(
            panel.iloc[train_idx],
            panel.iloc[train_idx]["y"],
            n_trials=1,
            feature_cols=feature_cols,
            num_boost_round=40,
        )
        pred = model.predict(panel.iloc[test_idx])
        aligned = pd.DataFrame(
            {
                "pred": pred["ml_pred"].to_numpy(),
                "y": panel.iloc[test_idx]["y"].to_numpy(),
            }
        ).dropna()
        if aligned.empty:
            continue
        ic = aligned["pred"].corr(aligned["y"], method="spearman")
        if ic == ic:
            ics.append(float(ic))
    assert ics, "IC を計算できる分割がありません"
    mean_ic = float(np.mean(ics))
    t_stat = mean_ic / (np.std(ics, ddof=1) / np.sqrt(len(ics))) if len(ics) > 1 else 0.0
    assert abs(t_stat) < 2.5, (
        f"ノイズデータから有意な予測力が検出されました（IC={mean_ic:.4f}, t={t_stat:.2f}）。"
        "パイプラインにリークがあります。"
    )
