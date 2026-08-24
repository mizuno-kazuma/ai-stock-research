"""テスト用の合成データ生成。

乱数は必ず seed を固定する。テストが日によって落ちる状態は、リーク検出のような
「落ちたら必ず調べる」テストの信頼性を壊す。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

DEFAULT_START = date(2024, 1, 1)


def business_days(start: date, n: int) -> list[date]:
    return [d.date() for d in pd.bdate_range(start, periods=n)]


def make_prices(
    tickers: list[str],
    *,
    n_days: int = 320,
    start: date = DEFAULT_START,
    market: str = "JP",
    seed: int = 42,
    base_price: float = 1000.0,
) -> pd.DataFrame:
    """`prices_daily` 形式の合成価格。幾何ブラウン運動。"""
    rng = np.random.default_rng(seed)
    days = business_days(start, n_days)
    rows: list[dict[str, object]] = []
    for i, ticker in enumerate(tickers):
        drift = 0.0002 * (1 + i % 3)
        vol = 0.012 * (1 + 0.3 * (i % 4))
        shocks = rng.normal(drift, vol, size=n_days)
        closes = base_price * (1.0 + float(i)) * np.exp(np.cumsum(shocks))
        for j, day in enumerate(days):
            close = float(closes[j])
            open_ = close / (1.0 + float(shocks[j]) * 0.5)
            rows.append(
                {
                    "ticker": ticker,
                    "market": market,
                    "trade_date": day,
                    "open": open_,
                    "high": max(open_, close) * 1.004,
                    "low": min(open_, close) * 0.996,
                    "close": close,
                    "volume": float(1_000_000 + 5_000 * ((i + j) % 40)),
                    "turnover_value": close * (1_000_000 + 5_000 * ((i + j) % 40)),
                    "adj_open": open_,
                    "adj_high": max(open_, close) * 1.004,
                    "adj_low": min(open_, close) * 0.996,
                    "adj_close": close,
                    "adj_volume": float(1_000_000 + 5_000 * ((i + j) % 40)),
                    "adjustment_factor": 1.0,
                    "currency": "JPY" if market == "JP" else "USD",
                    "source": "jquants" if market == "JP" else "yfinance",
                    "quality_flags": [],
                    "ingested_at": datetime(2026, 1, 1),
                }
            )
    return pd.DataFrame(rows)


def make_securities(
    tickers: list[str], *, market: str = "JP", n_sectors: int = 4, shares: float = 5e8
) -> pd.DataFrame:
    rows = []
    for i, ticker in enumerate(tickers):
        rows.append(
            {
                "ticker": ticker,
                "market": market,
                "exchange": "TSE_PRIME" if market == "JP" else "NASDAQ",
                "name_local": f"テスト{ticker}",
                "name_en": f"Test {ticker}",
                "sector_code": f"S{i % n_sectors:02d}",
                "sector_name": f"sector-{i % n_sectors}",
                "currency": "JPY" if market == "JP" else "USD",
                "shares_outstanding": shares * (1 + i % 5),
                "listing_date": date(2010, 1, 4),
                "delisting_date": None,
                "is_active": True,
                "valid_from": date(2010, 1, 4),
                "valid_to": None,
                "ingested_at": datetime(2026, 1, 1),
            }
        )
    return pd.DataFrame(rows)


def make_financials(
    tickers: list[str],
    *,
    market: str = "JP",
    n_quarters: int = 16,
    first_period_end: date = date(2020, 3, 31),
    period_type: str = "quarter",
    seed: int = 7,
) -> pd.DataFrame:
    """`financials` 形式。`filed_at` は期末の45日後（日本の実務に近い）。"""
    rng = np.random.default_rng(seed)
    rows: list[dict[str, object]] = []
    for i, ticker in enumerate(tickers):
        revenue = 1e11 * (1 + i * 0.5)
        equity = 5e11 * (1 + i * 0.3)
        period_end = first_period_end
        for q in range(n_quarters):
            quarter = q % 4 + 1
            growth = 1.0 + 0.02 * q + float(rng.normal(0, 0.01))
            rows.append(
                {
                    "ticker": ticker,
                    "market": market,
                    "period_end": period_end,
                    "fiscal_year": period_end.year,
                    "fiscal_period": f"Q{quarter}",
                    "period_type": period_type,
                    "filed_at": period_end + timedelta(days=45),
                    "revenue": revenue * growth / 4,
                    "operating_income": revenue * growth * 0.10 / 4,
                    "ordinary_income": revenue * growth * 0.095 / 4,
                    "net_income": revenue * growth * 0.07 / 4,
                    "eps": 30.0 * growth,
                    "total_assets": equity * 2.1,
                    "total_equity": equity * growth,
                    "total_debt": equity * 0.4,
                    "cash_and_equiv": equity * 0.2,
                    "operating_cf": revenue * growth * 0.09 / 4,
                    "investing_cf": -revenue * growth * 0.04 / 4,
                    "financing_cf": -revenue * growth * 0.01 / 4,
                    "capex": revenue * growth * 0.035 / 4,
                    "ebitda": revenue * growth * 0.15 / 4,
                    "cogs": revenue * growth * 0.65 / 4,
                    "interest_expense": revenue * 0.002 / 4,
                    "tax_expense": revenue * growth * 0.03 / 4,
                    "pretax_income": revenue * growth * 0.10 / 4,
                    "dividend_per_share": 8.0,
                    "bps": 500.0 * growth,
                    "forecast_revenue": revenue * growth * 1.05,
                    "forecast_op_income": revenue * growth * 0.11,
                    "forecast_net_income": revenue * growth * 0.075,
                    "forecast_eps": 32.0 * growth,
                    "accounting_standard": "JGAAP" if market == "JP" else "USGAAP",
                    "currency": "JPY" if market == "JP" else "USD",
                    "unit_multiplier": 1,
                    "is_restated": False,
                    "source": "jquants" if market == "JP" else "edgar",
                    "ingested_at": datetime(2026, 1, 1),
                }
            )
            month = period_end.month + 3
            year = period_end.year + (month - 1) // 12
            month = (month - 1) % 12 + 1
            day = 31 if month in (3, 12) else 30
            period_end = date(year, month, min(day, 30 if month in (6, 9) else 31))
    return pd.DataFrame(rows)


def make_macro_series(
    series_id: str = "DEXJPUS",
    *,
    n_days: int = 320,
    start: date = DEFAULT_START,
    seed: int = 11,
    base: float = 150.0,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = business_days(start, n_days)
    values = base * np.exp(np.cumsum(rng.normal(0.0001, 0.005, size=n_days)))
    return pd.DataFrame(
        {
            "series_id": series_id,
            "observation_date": days,
            # 日次系列（為替・金利）は改訂されないため vintage = observation。
            "vintage_date": days,
            "value": values,
            "unit": "JPY/USD",
            "frequency": "D",
            "source": "fred",
            "ingested_at": datetime(2026, 1, 1),
        }
    )
