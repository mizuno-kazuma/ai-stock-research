"""推奨からETF・REITを除外する（docs/05-scoring-screening.md §7.1a）。

`UniverseFilter.common_stock_only`（既定 True）は `securities.product_category`
が `'011'`（内国株券）以外の行を除外する。Strategist は `scores_daily` に
`securities` の現行 `product_category` を突き合わせてからこのフィルタを適用する。
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from services.agent.jobs.strategist import strategist
from tests.fakes import FakeStateRepo, FakeWarehouse
from tests.unit.agent.test_agent_loop import _score_frame


def _etf_row(as_of: date) -> dict:
    row = _score_frame(as_of).iloc[0].to_dict()
    row["ticker"] = "15600"
    return row


def test_strategist_excludes_etf_from_recommendations() -> None:
    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    as_of = date(2026, 8, 21)

    scores = pd.concat(
        [_score_frame(as_of), pd.DataFrame([_etf_row(as_of)])], ignore_index=True
    )
    warehouse.scores = scores
    warehouse.securities = pd.DataFrame(
        [
            {"ticker": "7203", "market": "JP", "product_category": "011"},
            {"ticker": "15600", "market": "JP", "product_category": "014"},
        ]
    )
    warehouse.doc_text["quant:scores_daily"] = "定量スコアとML予測区間に基づく自動生成カードです。"
    warehouse.documents["quant:scores_daily"] = {
        "doc_id": "quant:scores_daily",
        "filed_at": as_of,
        "ticker": "7203",
    }

    result = strategist(
        "JP",
        as_of,
        state=state,
        warehouse=warehouse,
        memory=state,
        router=None,
        scores=scores,
    )

    tickers = {rec["ticker"] for rec in result.recs}
    assert tickers == {"7203"}
    assert "15600" not in {rec["ticker"] for rec in warehouse.recs}


def test_strategist_includes_etf_when_common_stock_only_disabled() -> None:
    from packages.core.factors.screening import UniverseFilter

    state = FakeStateRepo()
    warehouse = FakeWarehouse()
    as_of = date(2026, 8, 21)

    scores = pd.concat(
        [_score_frame(as_of), pd.DataFrame([_etf_row(as_of)])], ignore_index=True
    )
    warehouse.scores = scores
    warehouse.securities = pd.DataFrame(
        [
            {"ticker": "7203", "market": "JP", "product_category": "011"},
            {"ticker": "15600", "market": "JP", "product_category": "014"},
        ]
    )
    warehouse.doc_text["quant:scores_daily"] = "定量スコアとML予測区間に基づく自動生成カードです。"
    warehouse.documents["quant:scores_daily"] = {
        "doc_id": "quant:scores_daily",
        "filed_at": as_of,
        "ticker": "7203",
    }

    result = strategist(
        "JP",
        as_of,
        state=state,
        warehouse=warehouse,
        memory=state,
        router=None,
        scores=scores,
        universe_filter=UniverseFilter(market="JP", common_stock_only=False),
    )

    tickers = {rec["ticker"] for rec in result.recs}
    assert tickers == {"7203", "15600"}
