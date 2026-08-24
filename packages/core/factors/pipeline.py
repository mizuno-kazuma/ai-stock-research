"""特徴量計算のパイプライン。`features_daily` 1日分を組み立てる。

入口は必ず `PitContext`。生の DataFrame を直接受け取る経路を作らないのは、
`as_of` で切る処理を呼び忘れる余地を消すため。

登録する入力（`PitContext.add*`）:

| 名前 | 内容 | 時間軸 |
| --- | --- | --- |
| `prices` | `prices_daily`（`prices_live` は禁止） | `trade_date` |
| `securities` | `securities`（当時のセクター・発行済株式数） | `valid_from` |
| `financials` | `financials`（訂正含む全版） | `filed_at` |
| `benchmark` | ベンチマーク価格（TOPIX / S&P500） | `trade_date` |
| `fx` | USD/JPY 日次（`macro_series` の `DEXJPUS`） | `observation_date` |
| `macro` | その他マクロ | `vintage_date` |
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from packages.core.factors.fundamentals import compute_fundamentals
from packages.core.factors.fx import compute_fx_features
from packages.core.factors.liquidity import compute_liquidity
from packages.core.factors.panel import PricePanel
from packages.core.factors.pit_guard import PitContext, assert_no_future_rows
from packages.core.factors.registry import (
    FEATURE_COLUMNS,
    MAX_MISSING_FEATURES,
    WINSORIZE_COLUMNS,
)
from packages.core.factors.returns import (
    compute_momentum,
    compute_returns,
    compute_sector_relative,
)
from packages.core.factors.technicals import compute_technicals
from packages.core.factors.transforms import winsorize_frame
from packages.core.factors.volatility import compute_volatility

#: 定義変更時に採番する。`features_daily` の主キーに含まれる。
FEATURE_VERSION = "v1.0.0"

META_COLUMNS = (
    "ticker",
    "market",
    "as_of",
    "market_cap",
    "currency",
    "feature_version",
    "n_missing",
    "computed_at",
)


def build_pit_context(
    *,
    as_of: date,
    market: str,
    prices: pd.DataFrame,
    securities: pd.DataFrame | None = None,
    financials: pd.DataFrame | None = None,
    benchmark: pd.DataFrame | None = None,
    fx: pd.DataFrame | None = None,
    macro: pd.DataFrame | None = None,
) -> PitContext:
    """入力を `PitContext` に詰める。欠けた入力はそのまま登録しない（機能縮退）。"""
    from packages.core.factors.calendar import TradingCalendar

    calendar = TradingCalendar.from_prices(prices)
    context = PitContext(as_of=as_of, market=market, calendar=calendar)
    context.add("prices", prices, "trade_date")
    if securities is not None and not securities.empty:
        time_col = "valid_from" if "valid_from" in securities.columns else "ingested_at"
        context.add("securities", securities, time_col)
    if financials is not None and not financials.empty:
        context.add("financials", financials, "filed_at")
    if benchmark is not None and not benchmark.empty:
        context.add("benchmark", benchmark, "trade_date")
    if fx is not None and not fx.empty:
        time_col = "vintage_date" if "vintage_date" in fx.columns else "observation_date"
        context.add("fx", fx, time_col)
    if macro is not None and not macro.empty:
        context.add("macro", macro, "vintage_date")
    return context


def _security_attributes(context: PitContext, tickers: list[str]) -> pd.DataFrame:
    """当時のセクターと発行済株式数。

    過去のバックテストで「当時のセクター」を使わないとセクター中立化が壊れる
    （docs/03-data-model.md §2.1）。
    """
    index = pd.Index(tickers, name="ticker")
    empty = pd.DataFrame(
        {
            "sector_code": pd.Series(index=index, dtype=object),
            "shares_outstanding": pd.Series(index=index, dtype="float64"),
            "currency": pd.Series(index=index, dtype=object),
            "listing_date": pd.Series(index=index, dtype=object),
            "delisting_date": pd.Series(index=index, dtype=object),
        }
    )
    securities = context.optional("securities")
    if securities is None:
        return empty
    work = securities.copy()
    work["ticker"] = work["ticker"].astype(str)
    time_col = "valid_from" if "valid_from" in work.columns else "ingested_at"
    work = work.sort_values(["ticker", time_col], kind="mergesort")
    latest = work.groupby("ticker", as_index=False, sort=False).tail(1).set_index("ticker")
    for col in empty.columns:
        if col in latest.columns:
            empty[col] = latest[col].reindex(index)
    return empty


def _series_from_frame(
    frame: pd.DataFrame | None, *, value_col: str, date_col: str
) -> pd.Series | None:
    if frame is None or frame.empty:
        return None
    if value_col not in frame.columns or date_col not in frame.columns:
        return None
    work = frame[[date_col, value_col]].dropna()
    if work.empty:
        return None
    work = work.drop_duplicates(subset=[date_col], keep="last")
    series = pd.Series(
        pd.to_numeric(work[value_col], errors="coerce").to_numpy(),
        index=pd.to_datetime(work[date_col]),
    ).sort_index()
    return series


def compute_features(context: PitContext, *, benchmark_ticker: str | None = None) -> pd.DataFrame:
    """`features_daily` 1日分を計算する。

    Returns:
        `features_daily` のスキーマに沿った DataFrame（1銘柄1行）。
    """
    as_of = context.as_of
    prices = context.get("prices")
    assert_no_future_rows(prices, as_of, "trade_date")
    panel = PricePanel.from_long(prices, as_of)
    if panel.is_empty:
        return _empty_features()

    attributes = _security_attributes(context, panel.tickers)
    sectors = attributes["sector_code"]
    latest_close = panel.last_row("adj_close")
    shares = pd.to_numeric(attributes["shares_outstanding"], errors="coerce")
    market_cap = (latest_close * shares.reindex(latest_close.index)).rename("market_cap")

    frames: list[pd.DataFrame] = [
        compute_returns(panel),
        compute_momentum(panel),
        compute_technicals(panel),
        compute_liquidity(panel, market_cap=market_cap),
    ]

    benchmark_returns = None
    benchmark = context.optional("benchmark")
    if benchmark is not None:
        bench_frame = benchmark
        if benchmark_ticker and "ticker" in bench_frame.columns:
            bench_frame = bench_frame.loc[bench_frame["ticker"].astype(str) == benchmark_ticker]
        bench_series = _series_from_frame(
            bench_frame, value_col="adj_close", date_col="trade_date"
        )
        if bench_series is not None and len(bench_series) > 1:
            benchmark_returns = np.log(bench_series.where(bench_series > 0)).diff()
    frames.append(compute_volatility(panel, benchmark_returns=benchmark_returns))

    fx_frame = context.optional("fx")
    fx_series = None
    if fx_frame is not None:
        date_col = "observation_date" if "observation_date" in fx_frame.columns else "trade_date"
        fx_series = _series_from_frame(fx_frame, value_col="value", date_col=date_col)
        if fx_series is None:
            fx_series = _series_from_frame(fx_frame, value_col="adj_close", date_col=date_col)
    frames.append(compute_fx_features(panel, fx_series))

    financials = context.optional("financials")
    if financials is not None:
        frames.append(
            compute_fundamentals(
                financials,
                as_of,
                market_cap=market_cap,
                close=latest_close,
                market=context.market,
            ).drop(columns=["latest_filed_at"], errors="ignore")
        )

    features = pd.concat([f for f in frames if not f.empty], axis=1)
    features = features.reindex(pd.Index(panel.tickers, name="ticker"))
    features["sector_relative_ret_20d"] = compute_sector_relative(features, sectors)

    out = features.reindex(columns=list(FEATURE_COLUMNS))
    out.insert(0, "market", context.market)
    out.insert(1, "as_of", as_of)
    out["market_cap"] = market_cap.reindex(out.index)
    out["currency"] = attributes["currency"].reindex(out.index).fillna(
        "JPY" if context.market == "JP" else "USD"
    )
    out["feature_version"] = FEATURE_VERSION
    out["n_missing"] = out[list(FEATURE_COLUMNS)].isna().sum(axis=1).astype(int)
    out["computed_at"] = datetime.now(UTC)
    return out.reset_index()


def _empty_features() -> pd.DataFrame:
    columns = ["ticker", "market", "as_of", *FEATURE_COLUMNS, *META_COLUMNS[3:]]
    return pd.DataFrame(columns=list(dict.fromkeys(columns)))


def prepare_cross_section(
    features: pd.DataFrame,
    *,
    winsorize_lower: float = 0.01,
    winsorize_upper: float = 0.99,
) -> pd.DataFrame:
    """断面前処理。比率系の特徴量を日・市場内で winsorize する。"""
    if features.empty:
        return features.copy()
    return winsorize_frame(
        features,
        list(WINSORIZE_COLUMNS),
        group_cols=["as_of", "market"],
        lower=winsorize_lower,
        upper=winsorize_upper,
    )


def drop_incomplete(
    features: pd.DataFrame, *, max_missing: int = MAX_MISSING_FEATURES
) -> pd.DataFrame:
    """欠損が多すぎる銘柄をその日のスコアリング対象から除外する。"""
    if features.empty or "n_missing" not in features.columns:
        return features.copy()
    return features.loc[features["n_missing"] <= max_missing].reset_index(drop=True)


def compute_features_range(
    context: PitContext, as_of_dates: list[date], **kwargs: object
) -> pd.DataFrame:
    """複数日分をまとめて計算する。バックテストと学習データ作成に使う。

    日ごとに `as_of` を差し替えるため、ある日の計算が後の日のデータを見ることはない。
    """
    frames: list[pd.DataFrame] = []
    for as_of in sorted(as_of_dates):
        chunk = compute_features(context.with_as_of(as_of), **kwargs)  # type: ignore[arg-type]
        if not chunk.empty:
            frames.append(chunk)
    if not frames:
        return _empty_features()
    return pd.concat(frames, ignore_index=True)
