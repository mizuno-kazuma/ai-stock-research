"""リーク検証（T-LEAK 系）。

`.cursor/skills/add-analysis-factor/SKILL.md` の必須チェック。未来データを追加しても
特徴量が1つも変わらないことを確認する。ここが落ちたら他のテストの結果は信用できない。
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from packages.core.factors.calendar import TradingCalendar, effective_date
from packages.core.factors.fundamentals import pit_financials
from packages.core.factors.pipeline import build_pit_context, compute_features
from packages.core.factors.pit_guard import (
    LeakError,
    PitContext,
    assert_no_future_rows,
    assert_stable_under_future_data,
    future_rows_like,
)
from packages.core.factors.registry import FEATURE_COLUMNS
from tests.factories import (
    make_financials,
    make_macro_series,
    make_prices,
    make_securities,
)

TICKERS = ["1001", "1002", "1003", "1004", "1005", "1006", "1007", "1008", "1009", "1010"]
AS_OF = date(2024, 12, 2)


@pytest.fixture(scope="module")
def inputs() -> dict[str, pd.DataFrame]:
    # mom_12_1 は 253 営業日の履歴が要る。as_of=2024-12-02 から見て足りる開始日にする。
    prices = make_prices(TICKERS, n_days=520, start=date(2022, 11, 1))
    return {
        "prices": prices,
        "securities": make_securities(TICKERS),
        "financials": make_financials(TICKERS),
        "fx": make_macro_series(),
    }


@pytest.fixture(scope="module")
def context(inputs: dict[str, pd.DataFrame]) -> PitContext:
    return build_pit_context(
        as_of=AS_OF,
        market="JP",
        prices=inputs["prices"],
        securities=inputs["securities"],
        financials=inputs["financials"],
        fx=inputs["fx"],
    )


def test_features_do_not_change_when_future_data_is_appended(
    context: PitContext, inputs: dict[str, pd.DataFrame]
) -> None:
    """T-LEAK: 未来行を足しても全特徴量が一致すること。"""
    future = {
        "prices": future_rows_like(
            inputs["prices"], time_col="trade_date", as_of=AS_OF, days=20
        ),
        "financials": future_rows_like(
            inputs["financials"], time_col="filed_at", as_of=AS_OF, days=10
        ),
        "fx": future_rows_like(
            inputs["fx"], time_col="observation_date", as_of=AS_OF, days=20
        ),
    }
    baseline = assert_stable_under_future_data(
        compute_features,
        context,
        future,
        compare_cols=["ticker", *FEATURE_COLUMNS],
        label="features_daily",
    )
    assert not baseline.empty
    # 検証が空振りしていないこと（そもそも値が入っているか）を確かめる。
    assert baseline["ret_20d"].notna().any()
    assert baseline["mom_12_1"].notna().any()
    assert baseline["earnings_yield"].notna().any()


def test_leak_detector_actually_catches_a_leak(
    context: PitContext, inputs: dict[str, pd.DataFrame]
) -> None:
    """検証器そのものの検証。意図的にリークさせたら必ず落ちること。"""

    def leaky(ctx: PitContext) -> pd.DataFrame:
        # `visible` を経由せず生データを直接見る = 未来を見る。
        raw = ctx.inputs["prices"].frame
        latest = (
            raw.sort_values("trade_date")
            .groupby("ticker")["adj_close"]
            .last()
            .rename("leaky_feature")
        )
        return latest.to_frame().reset_index()

    future = {
        "prices": future_rows_like(
            inputs["prices"], time_col="trade_date", as_of=AS_OF, days=5
        )
    }
    with pytest.raises(LeakError):
        assert_stable_under_future_data(leaky, context, future, label="leaky")


def test_pit_frame_hides_future_rows(inputs: dict[str, pd.DataFrame]) -> None:
    context = build_pit_context(as_of=AS_OF, market="JP", prices=inputs["prices"])
    visible = context.get("prices")
    assert visible["trade_date"].max() <= AS_OF
    assert_no_future_rows(visible, AS_OF, "trade_date")


def test_assert_no_future_rows_raises() -> None:
    frame = pd.DataFrame({"trade_date": [date(2024, 12, 3)], "x": [1.0]})
    with pytest.raises(LeakError):
        assert_no_future_rows(frame, AS_OF, "trade_date")


def test_financials_are_filtered_by_filed_at_not_period_end() -> None:
    """`period_end <= as_of` で絞ると未来情報になる（提出は期末の1-3ヶ月後）。"""
    financials = make_financials(["1001"], n_quarters=8)
    as_of = date(2021, 5, 1)
    pit = pit_financials(financials, as_of)
    assert (pd.Series(pit["filed_at"]) <= as_of).all()
    # 期末が as_of 以前でも未提出の期間は含まれない。
    unfiled = financials.loc[
        (financials["period_end"] <= as_of) & (financials["filed_at"] > as_of)
    ]
    assert not unfiled.empty, "テストデータが前提を満たしていない"
    assert not set(pit["period_end"]) & set(unfiled["period_end"])


def test_restatements_use_the_latest_filed_version() -> None:
    base = make_financials(["1001"], n_quarters=4)
    restated = base.tail(1).copy()
    restated["filed_at"] = restated["filed_at"] + pd.Timedelta(days=30)
    restated["net_income"] = restated["net_income"] * 0.5
    restated["is_restated"] = True
    combined = pd.concat([base, restated], ignore_index=True)

    as_of_before = restated["filed_at"].iloc[0] - pd.Timedelta(days=1)
    as_of_before_d = as_of_before.date() if hasattr(as_of_before, "date") else as_of_before
    filed_d = restated["filed_at"].iloc[0]
    filed_d = filed_d.date() if hasattr(filed_d, "date") else filed_d
    before = pit_financials(combined, as_of_before_d)
    after = pit_financials(combined, filed_d)

    period_end = restated["period_end"].iloc[0]
    original = base.loc[base["period_end"] == period_end, "net_income"].iloc[0]
    assert before.loc[before["period_end"] == period_end, "net_income"].iloc[0] == original
    assert after.loc[after["period_end"] == period_end, "net_income"].iloc[0] == pytest.approx(
        original * 0.5
    )


@pytest.mark.parametrize(
    ("disclosed", "expected"),
    [
        # 15:00 前の開示は当日織り込める。
        (datetime(2024, 12, 2, 14, 59), date(2024, 12, 2)),
        # 15:00 以降は翌営業日。これを省くと「決算発表当日の終値で決算内容を
        # 知っていた」というリークが入る。
        (datetime(2024, 12, 2, 15, 0), date(2024, 12, 3)),
        (datetime(2024, 12, 2, 16, 30), date(2024, 12, 3)),
        # 金曜の引け後は月曜。
        (datetime(2024, 12, 6, 16, 0), date(2024, 12, 9)),
        # 土曜の開示は月曜。
        (datetime(2024, 12, 7, 10, 0), date(2024, 12, 9)),
    ],
)
def test_effective_date_applies_the_15_00_rule(disclosed: datetime, expected: date) -> None:
    assert effective_date(disclosed, "JP") == expected


def test_effective_date_us_cutoff_is_16_00() -> None:
    assert effective_date(datetime(2024, 12, 2, 15, 30), "US") == date(2024, 12, 2)
    assert effective_date(datetime(2024, 12, 2, 16, 0), "US") == date(2024, 12, 3)


def test_disclosure_based_input_uses_available_from(inputs: dict[str, pd.DataFrame]) -> None:
    documents = pd.DataFrame(
        {
            "doc_id": ["d1", "d2"],
            "ticker": ["1001", "1002"],
            "disclosed_at": [
                datetime(2024, 12, 2, 14, 0),
                datetime(2024, 12, 2, 16, 0),
            ],
        }
    )
    context = PitContext(as_of=AS_OF, market="JP", calendar=TradingCalendar())
    context.add_disclosure_based("documents", documents, disclosed_col="disclosed_at")
    visible = context.get("documents")
    # 引け後開示（d2）は as_of=当日 では見えない。
    assert list(visible["doc_id"]) == ["d1"]


def test_cross_sectional_zscore_does_not_use_other_days() -> None:
    """断面 z-score は同一日内で計算する。日付を跨ぐと未来の分布を使う。"""
    from packages.core.factors.transforms import cross_sectional_zscore

    frame = pd.DataFrame(
        {
            "as_of": [date(2024, 1, 1)] * 10 + [date(2024, 1, 2)] * 10,
            "sector_code": ["A"] * 20,
            "x": list(range(10)) + [v * 100 for v in range(10)],
        }
    )
    z = cross_sectional_zscore(frame, "x")
    day1 = z.iloc[:10].to_numpy()
    day2 = z.iloc[10:].to_numpy()
    # スケールが100倍違っても、同一日内の相対位置は同じになる。
    assert day1 == pytest.approx(day2)


def test_history_shortage_yields_null_not_zero(inputs: dict[str, pd.DataFrame]) -> None:
    """履歴不足は NULL。ゼロ埋めは「平均的な銘柄」という誤情報を注入する。"""
    short = make_prices(["9999"], n_days=30)
    context = build_pit_context(
        as_of=short["trade_date"].max(), market="JP", prices=short
    )
    features = compute_features(context)
    assert features["ret_252d"].isna().all()
    assert features["mom_12_1"].isna().all()
    assert features["ret_20d"].notna().all()
