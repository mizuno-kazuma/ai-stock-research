"""J-Quants API（日本株の価格・財務）。

docs/02-data-ingestion.md §2。`[要検証]` の注記があるエンドポイントパス・
認証方式・レート制限は、実装着手時に公式ドキュメントで確認する。
本モジュールでは以下を構造で担保する。

- 認証方式が v1 / v2 のどちらでも差し替えられる（`JQuantsAuth`）
- プラン（free / light）依存の値を1箇所から導出する
- 日足は **日付単位** で取得する（銘柄単位では 5 req/min で成立しない）
- 銘柄コードは必ず文字列（`7203` の先頭ゼロ落ち、`130A` に対応）
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any, Protocol

import pandas as pd

from packages.core.connectors.base import (
    Checkpoint,
    FetchWindow,
    HttpConnector,
    RawBatch,
    now_utc,
    tag_table,
)
from packages.core.connectors.errors import ConfigurationError, NotFoundError, SchemaDriftError
from packages.core.connectors.quality import validate_price_frame
from packages.core.connectors.sources_config import jquants_plan_params

EP_MASTER = "equities_master"
EP_BARS_DAILY = "equities_bars_daily"
EP_FINS_SUMMARY = "fins_summary"

# `[要検証]` 調査時点のパス。公式APIリファレンスで最新を確認する。
ENDPOINT_PATHS = {
    EP_MASTER: "/v2/equities/master",
    EP_BARS_DAILY: "/v2/equities/bars/daily",
    EP_FINS_SUMMARY: "/v2/fins/summary",
}

# 東証以外のサフィックス。v2 の MktNm（プライム等）と英語キーの両方を見る。
MARKET_SUFFIX = {
    "TSE_PRIME": ".T",
    "TSE_STANDARD": ".T",
    "TSE_GROWTH": ".T",
    "プライム": ".T",
    "スタンダード": ".T",
    "グロース": ".T",
    "prime": ".T",
    "standard": ".T",
    "growth": ".T",
    "SAPPORO": ".S",
    "NAGOYA": ".N",
    "FUKUOKA": ".F",
    "札幌": ".S",
    "名古屋": ".N",
    "福岡": ".F",
}


class JQuantsAuth(Protocol):
    """認証方式を差し替え可能にするための Protocol。

    v2 は `x-api-key` 想定だが、v1 方式（refresh token → id token）が
    現行だった場合に備えて切り出しておく。
    """

    def headers(self) -> dict[str, str]: ...


class ApiKeyAuth:
    """v2 想定。`x-api-key` ヘッダ。"""

    def __init__(self, api_key: str | None) -> None:
        self._key = api_key

    def headers(self) -> dict[str, str]:
        if not self._key:
            return {}
        return {"x-api-key": self._key}


class RefreshTokenAuth:
    """v1 互換のフォールバック。

    id token の取得は呼び出し可能オブジェクトとして注入する（本モジュールが
    追加のHTTP経路を持たないようにするため）。
    """

    def __init__(self, id_token_provider: Any) -> None:
        self._provider = id_token_provider

    def headers(self) -> dict[str, str]:
        token = self._provider()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}


class JQuantsConnector(HttpConnector):
    source = "jquants"

    required_payload_keys = {
        EP_MASTER: (),
        EP_BARS_DAILY: (),
        EP_FINS_SUMMARY: (),
    }

    def __init__(self, *, plan: str | None = None, auth: JQuantsAuth | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        resolved_plan = plan or self.config.get("plan") or "free"
        if isinstance(resolved_plan, str) and resolved_plan.startswith("${"):
            # sources.yaml のプレースホルダが解決されていない場合は環境変数を見る。
            env = self.env if self.env is not None else None
            import os

            source = env if env is not None else os.environ
            resolved_plan = source.get("JQUANTS_PLAN", "free")
        self.plan_params = jquants_plan_params(str(resolved_plan))
        self.plan = self.plan_params["plan"]
        self.rate_limit_per_min = int(self.plan_params["rate_limit_per_min"])
        self.delay_weeks = int(self.plan_params["delay_weeks"])
        self.history_years = int(self.plan_params["history_years"])
        self.yfinance_gap_fill = bool(self.plan_params["yfinance_gap_fill"])
        self.auth: JQuantsAuth = auth or ApiKeyAuth(self.config.secret(self.env))
        # sources.yaml は無料プランの 5 req/min を既定にしている。プラン派生値で上書きする。
        bucket = getattr(self.http, "bucket", None)
        if bucket is not None:
            bucket.rate_per_min = float(self.rate_limit_per_min)
            bucket.burst = max(1.0, min(float(self.rate_limit_per_min), 5.0))

    # ------------------------------------------------------------------
    def url(self, endpoint: str) -> str:
        return f"{self.config.base_url.rstrip('/')}{ENDPOINT_PATHS[endpoint]}"

    def require_credentials(self) -> None:
        if not self.auth.headers():
            raise ConfigurationError(
                "JQUANTS_API_KEY が設定されていません。"
                ".env を確認してください（値はログに出力しません）"
            )

    # ------------------------------------------------------------------
    def fetch(  # type: ignore[override]
        self,
        window: FetchWindow,
        *,
        endpoint: str = EP_BARS_DAILY,
        persist: bool = True,
        **kwargs: Any,
    ) -> Iterator[RawBatch]:
        """日付単位のループで生レスポンスを yield する。

        `endpoint=EP_MASTER` は週1回で十分なため単発呼び出しになる。
        """
        self.require_credentials()
        headers = self.auth.headers()

        if endpoint == EP_MASTER:
            yield from self._fetch_master(window, headers=headers, persist=persist)
            return

        for day in window.business_days():
            unit = day.isoformat()
            if self._checkpoint.is_done(f"{endpoint}:{unit}"):
                continue
            try:
                yield from self._iter_pages(
                    endpoint, params={"date": unit}, headers=headers, as_of=day, persist=persist
                )
            except NotFoundError:
                # 休業日など。data_gaps に残すのは Collector 側の責務。
                self._checkpoint.mark_done(f"{endpoint}:{unit}")
                self._checkpoint.bump("not_found")
                continue
            self._checkpoint.mark_done(f"{endpoint}:{unit}")

    def _fetch_master(
        self, window: FetchWindow, *, headers: dict[str, str], persist: bool
    ) -> Iterator[RawBatch]:
        yield from self._iter_pages(
            EP_MASTER,
            params={"date": window.end.isoformat()},
            headers=headers,
            as_of=window.end,
            persist=persist,
        )
        self._checkpoint.mark_done(f"{EP_MASTER}:{window.end.isoformat()}")

    def _iter_pages(
        self,
        endpoint: str,
        *,
        params: dict[str, str],
        headers: dict[str, str],
        as_of: date,
        persist: bool,
    ) -> Iterator[RawBatch]:
        """`pagination_key` が続く限り同じ日付を取り切る。"""
        query = dict(params)
        while True:
            payload = self.http.get_json(
                self.url(endpoint), params=query, headers=headers, endpoint=endpoint
            )
            self._checkpoint.bump("api_calls")
            cursor = payload.get("pagination_key") if isinstance(payload, dict) else None
            yield self.make_batch(
                endpoint=endpoint,
                as_of=as_of,
                payload=payload,
                request=dict(query),
                next_cursor=cursor,
                persist=persist,
            )
            if not cursor:
                return
            query = {**params, "pagination_key": str(cursor)}

    # ------------------------------------------------------------------
    def normalize(self, batch: RawBatch) -> pd.DataFrame:
        self.assert_payload_shape(batch)
        if batch.endpoint == EP_BARS_DAILY:
            return self._normalize_prices(batch)
        if batch.endpoint == EP_MASTER:
            return self._normalize_master(batch)
        if batch.endpoint == EP_FINS_SUMMARY:
            return self._normalize_financials(batch)
        raise SchemaDriftError(
            f"未知のエンドポイント: {batch.endpoint}", source=self.source, endpoint=batch.endpoint
        )

    def _normalize_prices(self, batch: RawBatch) -> pd.DataFrame:
        rows = _payload_rows(batch.payload, "data", "daily_quotes")
        if not rows:
            return tag_table(_empty_prices_frame(), "prices_daily")
        raw = pd.DataFrame(rows)
        if "Code" not in raw.columns or "Date" not in raw.columns:
            raise SchemaDriftError(
                f"jquants/{batch.endpoint}: 必須フィールド Code/Date が欠けています",
                source=self.source,
                endpoint=batch.endpoint,
            )

        df = pd.DataFrame(
            {
                "ticker": raw["Code"].astype(str).str.strip(),
                "market": "JP",
                "trade_date": pd.to_datetime(raw["Date"]).dt.date,
                "open": _num(raw, "O", "Open"),
                "high": _num(raw, "H", "High"),
                "low": _num(raw, "L", "Low"),
                "close": _num(raw, "C", "Close"),
                "volume": _num(raw, "Vo", "Volume"),
                "turnover_value": _num(raw, "Va", "TurnoverValue"),
                "adj_open": _num(raw, "AdjO", "AdjustmentOpen"),
                "adj_high": _num(raw, "AdjH", "AdjustmentHigh"),
                "adj_low": _num(raw, "AdjL", "AdjustmentLow"),
                "adj_close": _num(raw, "AdjC", "AdjustmentClose"),
                "adj_volume": _num(raw, "AdjVo", "AdjustmentVolume"),
                "adjustment_factor": _num(raw, "AdjFactor", "AdjustmentFactor").fillna(1.0),
                "currency": "JPY",
                "source": self.source,
            }
        )
        # 調整値が来ないプラン・期間では無調整値で埋める（列自体は必ず持つ）。
        for col, fallback in [
            ("adj_open", "open"),
            ("adj_high", "high"),
            ("adj_low", "low"),
            ("adj_close", "close"),
            ("adj_volume", "volume"),
        ]:
            df[col] = df[col].where(df[col].notna(), df[fallback])

        accepted, rejected = validate_price_frame(df)
        accepted["ingested_at"] = now_utc()
        accepted.attrs["rejected"] = rejected
        return tag_table(accepted, "prices_daily")

    def _normalize_master(self, batch: RawBatch) -> pd.DataFrame:
        rows = _payload_rows(batch.payload, "data", "info")
        if not rows:
            return tag_table(pd.DataFrame(), "securities")
        raw = pd.DataFrame(rows)
        df = pd.DataFrame(
            {
                "ticker": _col(raw, "Code").astype(str).str.strip(),
                "market": "JP",
                "exchange": _col(raw, "MktNm", "MarketCodeName"),
                "name_local": _col(raw, "CoName", "CompanyName"),
                "name_en": _col(raw, "CoNameEn", "CompanyNameEnglish"),
                "sector_code": _as_str(raw, "S33", "Sector33Code"),
                "sector_name": _col(raw, "S33Nm", "Sector33CodeName"),
                "industry_name": _col(raw, "S17Nm", "Sector17CodeName"),
                "currency": "JPY",
                "valid_from": batch.as_of,
                "is_active": True,
                "ingested_at": now_utc(),
            }
        )
        df["yf_symbol"] = df["ticker"] + df["exchange"].map(_suffix_for_exchange).fillna(".T")
        names = df["name_local"].astype("string").str.strip()
        df["name_local"] = names.mask(names.isin(["", "<NA>"]), other=pd.NA).fillna(df["ticker"])
        return tag_table(df, "securities")

    def _normalize_financials(self, batch: RawBatch) -> pd.DataFrame:
        rows = _payload_rows(batch.payload, "data", "statements")
        if not rows:
            return tag_table(pd.DataFrame(), "financials")
        raw = pd.DataFrame(rows)
        fy_end = _col(raw, "CurFYEn", "CurrentFiscalYearEndDate")
        df = pd.DataFrame(
            {
                "ticker": _col(raw, "Code", "LocalCode").astype(str).str.strip(),
                "market": "JP",
                "period_end": _date(raw, "CurPerEn", "CurrentPeriodEndDate"),
                # PIT の基準は開示日。期末日ではない。
                "filed_at": _date(raw, "DiscDate", "DisclosedDate"),
                "fiscal_year": pd.to_datetime(fy_end, errors="coerce").dt.year,
                "fiscal_period": _period_series(raw).map(_fiscal_period),
                # 決算短信は期首からの累計で開示される。単独四半期に直す処理が
                # 必要なため、`quarter` ではなく `cumulative` と記録する
                # （docs/04-analysis-engine.md §1.6 の累計/単独判別）。
                "period_type": _period_series(raw).map(_period_type),
                "doc_id": _col(raw, "DiscNo", "DisclosureNumber"),
                "revenue": _num(raw, "Sales", "NetSales"),
                "operating_income": _num(raw, "OP", "OperatingProfit"),
                "ordinary_income": _num(raw, "OdP", "OrdinaryProfit"),
                "net_income": _num(raw, "NP", "Profit"),
                "eps": _num(raw, "EPS", "EarningsPerShare"),
                "total_assets": _num(raw, "TA", "TotalAssets"),
                "total_equity": _num(raw, "Eq", "Equity"),
                "operating_cf": _num(raw, "CFO", "CashFlowsFromOperatingActivities"),
                "investing_cf": _num(raw, "CFI", "CashFlowsFromInvestingActivities"),
                "financing_cf": _num(raw, "CFF", "CashFlowsFromFinancingActivities"),
                "cash_and_equiv": _num(raw, "CashEq", "CashAndEquivalents"),
                "dividend_per_share": _num(raw, "DivAnn", "ResultDividendPerShareAnnual"),
                "bps": _num(raw, "BPS", "BookValuePerShare"),
                "forecast_revenue": _num(raw, "FSales", "ForecastNetSales"),
                "forecast_op_income": _num(raw, "FOP", "ForecastOperatingProfit"),
                "forecast_net_income": _num(raw, "FNP", "ForecastProfit"),
                "forecast_eps": _num(raw, "FEPS", "ForecastEarningsPerShare"),
                "accounting_standard": _col(raw, "DocType", "TypeOfDocument"),
                "currency": "JPY",
                "source": self.source,
                "ingested_at": now_utc(),
            }
        )
        df["fiscal_year"] = pd.to_numeric(df["fiscal_year"], errors="coerce").astype("Int64")
        df = df[df["filed_at"].notna() & df["period_end"].notna()]
        return tag_table(df.reset_index(drop=True), "financials")

    # ------------------------------------------------------------------
    def checkpoint(self) -> Checkpoint:
        return self._checkpoint

    def backfill_window(self, today: date) -> FetchWindow:
        """初回バックフィルの期間。プランの履歴長と遅延から導出する。"""
        start = today - pd.Timedelta(days=365 * self.history_years)
        end = today - pd.Timedelta(weeks=self.delay_weeks)
        return FetchWindow(start=start.date(), end=end.date())

    def research_cutoff(self, today: date) -> date:
        """リサーチ用に信頼できる最新日（12週遅延を反映）。"""
        return (pd.Timestamp(today) - pd.Timedelta(weeks=self.delay_weeks)).date()


def yfinance_symbol(ticker: str, exchange: str | None) -> str:
    """日本株の yfinance ティッカー（`{code}.T` など）。"""
    return f"{ticker}{_suffix_for_exchange(exchange)}"


def _suffix_for_exchange(exchange: object) -> str:
    if not isinstance(exchange, str):
        return ".T"
    for key, suffix in MARKET_SUFFIX.items():
        if key.lower() in exchange.lower():
            return suffix
    return ".T"


def _period_series(df: pd.DataFrame) -> pd.Series:
    series = _col(df, "CurPerType", "TypeOfCurrentPeriod")
    filled = series.fillna("FY").astype(str).str.upper().str.strip()
    return filled.mask(filled.isin(["", "<NA>", "NAN", "NONE"]), other="FY")


def _fiscal_period(value: str) -> str:
    """`1Q` -> `Q1`。`4Q` は通期と同じ期間なので `FY` に寄せる。"""
    mapping = {"1Q": "Q1", "2Q": "Q2", "3Q": "Q3", "4Q": "FY", "FY": "FY", "": "FY"}
    return mapping.get(value, value)


def _period_type(value: str) -> str:
    if value in ("FY", "4Q", ""):
        return "annual"
    if value == "1Q":
        # 第1四半期は累計と単独が一致する。
        return "quarter"
    return "cumulative"


def _payload_rows(payload: Any, *keys: str) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    for key in keys:
        rows = payload.get(key)
        if isinstance(rows, list):
            return rows
    return []


def _num(df: pd.DataFrame, *columns: str) -> pd.Series:
    for column in columns:
        if column in df:
            return pd.to_numeric(df[column], errors="coerce")
    return pd.Series([pd.NA] * len(df), dtype="Float64").astype(float)


def _col(df: pd.DataFrame, *columns: str) -> pd.Series:
    """v1 正式名と v2 短縮名のどちらが来ても最初に存在する列を返す。"""
    for column in columns:
        if column in df.columns:
            return df[column]
    return pd.Series([None] * len(df), dtype=object)


def _as_str(df: pd.DataFrame, *columns: str) -> pd.Series:
    for column in columns:
        if column in df.columns:
            return df[column].astype(str)
    return pd.Series([None] * len(df), dtype=object)


def _date(df: pd.DataFrame, *columns: str) -> pd.Series:
    for column in columns:
        if column in df.columns:
            return pd.to_datetime(df[column], errors="coerce").dt.date
    return pd.Series([None] * len(df), dtype=object)


def _empty_prices_frame() -> pd.DataFrame:
    columns = [
        "ticker",
        "market",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "turnover_value",
        "adj_open",
        "adj_high",
        "adj_low",
        "adj_close",
        "adj_volume",
        "adjustment_factor",
        "currency",
        "source",
        "quality_flags",
        "ingested_at",
    ]
    return pd.DataFrame({c: pd.Series(dtype=object) for c in columns})
