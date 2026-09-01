"""TDnet（日本の適時開示）。

docs/02-data-ingestion.md §6。**公開APIではない**ため、以下を厳守する。

- 既定は無効（`TDNET_ENABLED=false`）。利用者が規約を確認した上で有効化する
- 日次バッチで1回のみ。ポーリング間隔の下限を10分とする
- 同時接続1。並列取得しない
- User-Agent に個人利用と連絡先を含める
- 失敗しても機能縮退する（TDnet を必須依存にしない）
- 取得内容を再配布しない

TDnet が使えない場合の代替経路（J-Quants 財務サマリの会社予想差分による
`guidance_revision` 検出）は `packages/core/factors/fundamentals.py` 側に置く。
"""

from __future__ import annotations

import re
from collections.abc import Iterator
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
from packages.core.connectors.errors import ConfigurationError, SchemaDriftError

EP_DISCLOSURES = "disclosures"

# docs/02-data-ingestion.md §6.2 の分類ルール。順序に意味がある
# （上方修正・下方修正はどちらも guidance_revision）。
TITLE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"決算短信"), "earnings_flash"),
    (re.compile(r"決算説明|説明資料|補足説明"), "earnings_presentation"),
    (re.compile(r"業績予想の(修正|下方修正|上方修正)|業績予想の修正"), "guidance_revision"),
    (re.compile(r"配当予想の修正"), "dividend_revision"),
    (re.compile(r"自己株式の取得"), "buyback"),
    (re.compile(r"株式分割"), "stock_split"),
    (re.compile(r"代表者の異動|役員の異動"), "management_change"),
]


def classify_title(title: str) -> str:
    """表題から `doc_type` を決める。"""
    text = str(title or "")
    for pattern, doc_type in TITLE_RULES:
        if pattern.search(text):
            return doc_type
    return "other_disclosure"


class TdnetConnector(HttpConnector):
    source = "tdnet"

    def __init__(self, *, contact: str | None = None, **kwargs: Any) -> None:
        # 既定で enabled: false なので require_enabled を尊重する。
        super().__init__(**kwargs)
        self.contact = contact or self.config.get("contact")
        self.min_poll_interval_min = int(self.config.get("min_poll_interval_min", 10))

    def auth_headers(self) -> dict[str, str]:
        """個人利用であることと連絡先を含める（規約上の礼儀）。"""
        contact = self.contact or "unknown"
        return {
            "User-Agent": (
                f"AI Stock Research Personal Tool (individual use; contact: {contact})"
            )
        }

    def require_credentials(self) -> None:
        if not self.contact:
            raise ConfigurationError(
                "TDnet へのアクセスには連絡先（TDNET_CONTACT）の設定が必要です。"
                "User-Agent に含めない自動取得は行いません"
            )

    # ------------------------------------------------------------------
    def fetch(  # type: ignore[override]
        self,
        window: FetchWindow,
        *,
        fetcher: Any = None,
        persist: bool = True,
        **kwargs: Any,
    ) -> Iterator[RawBatch]:
        """一覧を取得する。

        HTML のスクレイピング実装は規約と構造の確認が前提になるため、
        `fetcher(day) -> list[dict]` を注入する形にしてある。未注入の場合は
        空を返して機能縮退する（TDnet の欠損で全体を止めない）。
        """
        self.require_credentials()
        if fetcher is None:
            self._checkpoint.bump("skipped_no_fetcher")
            return
        for day in window.business_days():
            unit = f"{EP_DISCLOSURES}:{day.isoformat()}"
            if self._checkpoint.is_done(unit):
                continue
            rows = fetcher(day)
            self._checkpoint.bump("api_calls")
            yield self.make_batch(
                endpoint=EP_DISCLOSURES,
                as_of=day,
                payload={"disclosures": rows},
                request={"date": day.isoformat()},
                persist=persist,
            )
            self._checkpoint.mark_done(unit)

    # ------------------------------------------------------------------
    def normalize(self, batch: RawBatch) -> pd.DataFrame:
        payload = batch.payload or {}
        if "disclosures" not in payload:
            raise SchemaDriftError(
                "tdnet: payload に 'disclosures' がありません",
                source=self.source,
                endpoint=batch.endpoint,
            )
        rows = payload["disclosures"] or []
        if not rows:
            return tag_table(pd.DataFrame(), "documents")

        raw = pd.DataFrame(rows)
        titles = raw.get("title", pd.Series([""] * len(raw))).astype(str)
        seq = raw.get("seq", pd.Series(range(1, len(raw) + 1)))
        if "company_name" in raw.columns:
            names = raw["company_name"]
        elif "name" in raw.columns:
            names = raw["name"]
        else:
            names = pd.Series([None] * len(raw))
        df = pd.DataFrame(
            {
                "doc_id": [
                    f"tdnet:{batch.as_of:%Y%m%d}-{int(s):04d}" for s in pd.to_numeric(seq).tolist()
                ],
                "ticker": _normalize_code(raw.get("code")),
                "market": "JP",
                "name_local": names,
                "source": self.source,
                "doc_type": titles.map(classify_title),
                "form_code": None,
                "title": titles,
                "filed_at": pd.to_datetime(raw.get("disclosed_at"), errors="coerce"),
                "disclosed_at": pd.to_datetime(raw.get("disclosed_at"), errors="coerce"),
                "source_url": raw.get("document_url"),
                "pdf_url": raw.get("document_url"),
                "language": "ja",
                "is_amendment": False,
                "ingested_at": now_utc(),
            }
        )
        # TDnet は概ね30日で公開を終了するため、取得時のローカル保存が必須。
        df["should_download"] = True
        df = df[df["filed_at"].notna()]
        return tag_table(df.reset_index(drop=True), "documents")

    def checkpoint(self) -> Checkpoint:
        return self._checkpoint


def _normalize_code(series: Any) -> pd.Series:
    if series is None:
        return pd.Series(dtype=object)
    values = pd.Series(series).astype(object)

    def convert(value: Any) -> str | None:
        if value is None or pd.isna(value):
            return None
        text = str(value).strip()
        if len(text) == 5 and text.endswith("0"):
            return text[:4]
        return text or None

    return values.map(convert)


def next_allowed_poll(last_polled_at: pd.Timestamp, *, interval_min: int = 10) -> pd.Timestamp:
    """ポーリング間隔の下限を強制するためのヘルパ。"""
    return last_polled_at + pd.Timedelta(minutes=max(10, interval_min))


def detect_guidance_revision(
    financials: pd.DataFrame,
    *,
    ticker_col: str = "ticker",
    forecast_col: str = "forecast_op_income",
    filed_col: str = "filed_at",
) -> pd.DataFrame:
    """TDnet 無効時の代替経路（docs §6.3）。

    会社予想営業利益の前回開示比の差分から `guidance_revision` を検出する。
    TDnet を無効化しても主要機能が失われない構成にするために必要。
    """
    if financials.empty or forecast_col not in financials.columns:
        return pd.DataFrame(
            columns=[ticker_col, filed_col, "forecast_prev", "forecast_new", "direction", "magnitude"]
        )
    work = financials.sort_values([ticker_col, filed_col]).copy()
    work["forecast_prev"] = work.groupby(ticker_col)[forecast_col].shift(1)
    work = work[work["forecast_prev"].notna() & work[forecast_col].notna()]
    work["magnitude"] = work[forecast_col] / work["forecast_prev"].abs() - (
        work["forecast_prev"] / work["forecast_prev"].abs()
    )
    work["direction"] = 0
    work.loc[work[forecast_col] > work["forecast_prev"], "direction"] = 1
    work.loc[work[forecast_col] < work["forecast_prev"], "direction"] = -1
    return work.rename(columns={forecast_col: "forecast_new"})[
        [ticker_col, filed_col, "forecast_prev", "forecast_new", "direction", "magnitude"]
    ].reset_index(drop=True)
