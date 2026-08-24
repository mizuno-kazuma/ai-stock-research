"""yfinance（米国株の主ソース、日本株の直近ギャップ補完）。

docs/02-data-ingestion.md §3。非公式ライブラリであり、Yahoo Finance の
仕様変更で壊れる前提で扱う。

- `threads=False` を必須とする（並列化は 429 を誘発し、静かな欠損を生む）
- 1バッチ 50銘柄、バッチ間 1秒待機
- `auto_adjust=False` で無調整値と調整値の両方を保持する
- 日本株の直近12週は `prices_live`（現在値・参考値）に入れ、`prices_daily`
  とは**完全に分離する**。混ぜると遅延データを最新値として表示する事故になる
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Sequence
from datetime import date
from typing import Any

import pandas as pd

from packages.core.connectors.base import (
    Checkpoint,
    FetchWindow,
    HttpConnector,
    RawBatch,
    now_utc,
    tag_table,
)
from packages.core.connectors.errors import SchemaDriftError
from packages.core.connectors.quality import validate_price_frame

EP_DAILY = "download_daily"
EP_LIVE = "download_live"
DELAY_NOTE_JA = "約15-20分遅延"


def _default_downloader() -> Callable[..., pd.DataFrame]:
    """yfinance を遅延 import する。

    未インストールの環境でも本モジュールを import できるようにするため
    （テストではダウンローダを差し替える）。
    """

    def download(**kwargs: Any) -> pd.DataFrame:
        import yfinance as yf

        return yf.download(**kwargs)

    return download


class YFinanceConnector(HttpConnector):
    source = "yfinance"

    def __init__(
        self,
        *,
        downloader: Callable[..., pd.DataFrame] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        **kwargs: Any,
    ) -> None:
        # HTTP は yfinance ライブラリ側が担うため、共通クライアントは使わない。
        super().__init__(**kwargs)
        self._download = downloader or _default_downloader()
        self._sleep = sleep
        self.batch_size = int(self.config.get("batch_size", 50))
        self.batch_sleep_sec = float(self.config.get("batch_sleep_sec", 1.0))

    # ------------------------------------------------------------------
    def fetch(  # type: ignore[override]
        self,
        window: FetchWindow,
        *,
        symbols: Sequence[str],
        endpoint: str = EP_DAILY,
        persist: bool = True,
        **kwargs: Any,
    ) -> Iterator[RawBatch]:
        symbol_list = [str(s) for s in symbols]
        for index, batch_symbols in enumerate(_chunks(symbol_list, self.batch_size)):
            unit = f"{endpoint}:{index:04d}"
            if self._checkpoint.is_done(unit):
                continue
            if index > 0:
                self._sleep(self.batch_sleep_sec)
            frame = self._download(
                tickers=batch_symbols,
                start=window.start.isoformat(),
                # yfinance の end は排他的なので1日足す。
                end=(pd.Timestamp(window.end) + pd.Timedelta(days=1)).date().isoformat(),
                interval="1d",
                auto_adjust=False,
                actions=True,
                group_by="ticker",
                threads=False,  # 必須。並列化は部分欠損を静かに生む
                progress=False,
            )
            self._checkpoint.bump("api_calls")
            payload = _frame_to_payload(frame)
            request = {
                "tickers": batch_symbols,
                "start": window.start.isoformat(),
                "end": window.end.isoformat(),
            }
            yield self.make_batch(
                endpoint=endpoint,
                as_of=window.end,
                payload=payload,
                request=request,
                persist=persist,
            )
            self._checkpoint.mark_done(unit)

    # ------------------------------------------------------------------
    def normalize(self, batch: RawBatch) -> pd.DataFrame:
        rows = (batch.payload or {}).get("rows")
        if rows is None:
            raise SchemaDriftError(
                "yfinance: payload に 'rows' がありません",
                source=self.source,
                endpoint=batch.endpoint,
            )
        if not rows:
            return tag_table(pd.DataFrame(), "prices_daily")

        raw = pd.DataFrame(rows)
        market_map = batch.request.get("market_map") or {}
        currency_map = batch.request.get("currency_map") or {}

        df = pd.DataFrame(
            {
                "symbol": raw["symbol"].astype(str),
                "ticker": raw["symbol"].astype(str).map(_ticker_from_symbol),
                "trade_date": pd.to_datetime(raw["date"]).dt.date,
                "open": pd.to_numeric(raw.get("open"), errors="coerce"),
                "high": pd.to_numeric(raw.get("high"), errors="coerce"),
                "low": pd.to_numeric(raw.get("low"), errors="coerce"),
                "close": pd.to_numeric(raw.get("close"), errors="coerce"),
                "adj_close": pd.to_numeric(raw.get("adj_close"), errors="coerce"),
                "volume": pd.to_numeric(raw.get("volume"), errors="coerce"),
                "source": self.source,
            }
        )
        df["market"] = df["symbol"].map(lambda s: market_map.get(s, _market_from_symbol(s)))
        df["currency"] = df.apply(
            lambda r: currency_map.get(r["symbol"], "JPY" if r["market"] == "JP" else "USD"),
            axis=1,
        )
        df["adjustment_factor"] = (df["adj_close"] / df["close"]).where(df["close"] > 0, 1.0)
        for col, base in [("adj_open", "open"), ("adj_high", "high"), ("adj_low", "low")]:
            df[col] = df[base] * df["adjustment_factor"]
        df["adj_volume"] = df["volume"]
        df["turnover_value"] = df["close"] * df["volume"]

        accepted, rejected = validate_price_frame(df)
        accepted["ingested_at"] = now_utc()
        accepted.attrs["rejected"] = rejected
        accepted.attrs["reject_ratio"] = (
            len(rejected) / (len(rejected) + len(accepted)) if len(df) else 0.0
        )

        if batch.endpoint == EP_LIVE:
            return tag_table(_to_live_frame(accepted), "prices_live")
        return tag_table(accepted.drop(columns=["symbol"]), "prices_daily")

    def checkpoint(self) -> Checkpoint:
        return self._checkpoint

    # ------------------------------------------------------------------
    def needs_fallback(self, df: pd.DataFrame) -> bool:
        """Alpha Vantage / Finnhub へのフォールバック発動条件（docs §4.1）。

        品質チェックで 50% 以上の行が除外された場合を検出する。
        リトライ失敗回数と直近3営業日の欠損は Collector 側で判定する。
        """
        return float(df.attrs.get("reject_ratio", 0.0)) >= 0.5


def _to_live_frame(df: pd.DataFrame) -> pd.DataFrame:
    """`prices_live`（現在値・参考値）へ変換する。

    このテーブルはモデル学習・バックテスト・特徴量計算から参照禁止。
    """
    if df.empty:
        return df
    work = df.sort_values(["ticker", "trade_date"]).copy()
    work["prev_close"] = work.groupby("ticker")["close"].shift(1)
    work["change_pct"] = work["close"] / work["prev_close"] - 1.0
    return work[
        [
            "ticker",
            "market",
            "trade_date",
            "close",
            "prev_close",
            "change_pct",
            "volume",
            "currency",
            "source",
            "ingested_at",
        ]
    ].assign(is_delayed=True, delay_note=DELAY_NOTE_JA)


def _frame_to_payload(frame: pd.DataFrame) -> dict[str, Any]:
    """yfinance の MultiIndex 列を「行のリスト」に平坦化する。

    Raw層には無加工で残したいが、MultiIndex のままでは JSON にできない。
    列名の対応を保ったまま素直に縦持ちに直すだけで、値は一切変えない。
    """
    if frame is None or len(frame) == 0:
        return {"rows": []}

    records: list[dict[str, Any]] = []
    if isinstance(frame.columns, pd.MultiIndex):
        symbols = list(dict.fromkeys(frame.columns.get_level_values(0)))
        for symbol in symbols:
            sub = frame[symbol]
            for idx, row in sub.iterrows():
                records.append(_row_to_record(symbol, idx, row))
    else:
        symbol = str(frame.attrs.get("symbol", ""))
        for idx, row in frame.iterrows():
            records.append(_row_to_record(symbol, idx, row))
    return {"rows": records}


def _row_to_record(symbol: str, index: Any, row: pd.Series) -> dict[str, Any]:
    def pick(*names: str) -> Any:
        for name in names:
            if name in row.index:
                value = row[name]
                return None if pd.isna(value) else float(value)
        return None

    return {
        "symbol": symbol,
        "date": pd.Timestamp(index).date().isoformat(),
        "open": pick("Open", "open"),
        "high": pick("High", "high"),
        "low": pick("Low", "low"),
        "close": pick("Close", "close"),
        "adj_close": pick("Adj Close", "adj_close", "Close"),
        "volume": pick("Volume", "volume"),
        "dividends": pick("Dividends"),
        "splits": pick("Stock Splits"),
    }


def _ticker_from_symbol(symbol: str) -> str:
    """`7203.T` → `7203`、`AAPL` → `AAPL`。"""
    if "." in symbol:
        head, _, tail = symbol.rpartition(".")
        if tail.upper() in {"T", "S", "N", "F"}:
            return head
    return symbol


def _market_from_symbol(symbol: str) -> str:
    return "JP" if symbol.rpartition(".")[2].upper() in {"T", "S", "N", "F"} else "US"


def _chunks(items: Sequence[str], size: int) -> Iterator[list[str]]:
    for start in range(0, len(items), max(1, size)):
        yield list(items[start : start + size])


def usdjpy_symbol() -> str:
    """FRED の DEXJPUS が取れない場合の第2優先（docs §9）。"""
    return "JPY=X"


def business_day_before(today: date, n: int) -> date:
    return (pd.Timestamp(today) - pd.tseries.offsets.BDay(n)).date()
