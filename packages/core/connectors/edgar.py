"""SEC EDGAR（米国の開示資料・財務ファクト）。

docs/02-data-ingestion.md §7、docs/06-filings-access.md §4。

必須ルール:
- `User-Agent` に実名と連絡先メールアドレスを含める（未設定なら起動時にエラー）
- 10 req/s を超えない（本ツールでは安全側に 5 req/s）
- `Accept-Encoding: gzip` を付ける

PIT の要点: `companyfacts` は `end`（会計期間末日）ではなく **`filed`（提出日）**
を基準にする。`end` を基準にすると1ヶ月分の未来情報が漏れる。
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
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
from packages.core.connectors.errors import ConfigurationError, NotFoundError, SchemaDriftError

EP_SUBMISSIONS = "submissions"
EP_COMPANYFACTS = "companyfacts"
EP_TICKERS = "company_tickers"

# docs/02-data-ingestion.md §7.4
FORM_TO_DOC_TYPE = {
    "10-K": "annual_report",
    "10-K/A": "annual_report",
    "10-Q": "quarterly_report",
    "10-Q/A": "quarterly_report",
    "8-K": "current_report",
    "DEF 14A": "proxy",
    "SC 13D": "large_holding",
    "SC 13G": "large_holding",
    "4": "insider_transaction",
}
FULL_TEXT_FORMS = frozenset({"10-K", "10-Q", "10-K/A", "10-Q/A"})
# 8-K のうち抽出対象の Item（業績発表と役員異動のみ）
EIGHT_K_ITEMS_OF_INTEREST = ("2.02", "5.02")

# companyfacts から拾う US-GAAP タグ。複数候補を順に試す。
USGAAP_TAGS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ),
    "operating_income": ("OperatingIncomeLoss",),
    "net_income": ("NetIncomeLoss",),
    "eps": ("EarningsPerShareDiluted", "EarningsPerShareBasic"),
    "total_assets": ("Assets",),
    "total_equity": ("StockholdersEquity",),
    "total_debt": ("LongTermDebtNoncurrent", "LongTermDebt"),
    "cash_and_equiv": ("CashAndCashEquivalentsAtCarryingValue",),
    "operating_cf": ("NetCashProvidedByUsedInOperatingActivities",),
    "investing_cf": ("NetCashProvidedByUsedInInvestingActivities",),
    "financing_cf": ("NetCashProvidedByUsedInFinancingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "dividend_per_share": ("CommonStockDividendsPerShareDeclared",),
}

_UA_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(slots=True)
class EdgarUrls:
    submissions_json: str
    companyfacts_json: str
    filing_index: str
    primary_doc: str
    filing_summary: str
    all_files_index: str
    ixviewer: str


def validate_user_agent(user_agent: str | None) -> str:
    """`EDGAR_USER_AGENT` の検証（T-SEC-04）。

    空や連絡先のない値でアクセスするとブロックされ、復旧に時間がかかる。
    """
    if not user_agent or not user_agent.strip():
        raise ConfigurationError(
            "EDGAR_USER_AGENT が未設定です。実名と連絡先メールアドレスを含めてください"
        )
    if not _UA_RE.search(user_agent):
        raise ConfigurationError(
            "EDGAR_USER_AGENT に連絡先メールアドレスが含まれていません "
            "（例: 'AI Stock Research Personal Tool (you@example.com)'）"
        )
    return user_agent.strip()


def edgar_urls(cik: str, accession: str, primary_document: str) -> EdgarUrls:
    """CIK のゼロ埋めが URL の種類によって異なることに注意。

    - `data.sec.gov/submissions` と `companyfacts`: 10桁ゼロ埋め
    - `www.sec.gov/Archives` のパス: ゼロ埋めなしの整数

    この違いを取り違えると 404 になる。実装ミスが多い箇所である。
    """
    cik_digits = re.sub(r"\D", "", str(cik)) or "0"
    cik_padded = cik_digits.zfill(10)
    cik_int = str(int(cik_digits))
    accn_nodash = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}"
    doc_path = f"/Archives/edgar/data/{cik_int}/{accn_nodash}/{primary_document}"
    return EdgarUrls(
        submissions_json=f"https://data.sec.gov/submissions/CIK{cik_padded}.json",
        companyfacts_json=(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
        ),
        filing_index=f"{base}/{accession}-index.htm",
        primary_doc=f"{base}/{primary_document}" if primary_document else f"{base}/",
        filing_summary=f"{base}/FilingSummary.xml",
        all_files_index=f"{base}/",
        ixviewer=f"https://www.sec.gov/ix?doc={doc_path}" if primary_document else f"{base}/",
    )


def parse_submissions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """列指向の配列を行として組み立てる（docs/06-filings-access.md §4.2）。"""
    filings = payload.get("filings") or {}
    recent = filings.get("recent") or {}
    if "accessionNumber" not in recent:
        raise SchemaDriftError(
            "edgar/submissions: filings.recent.accessionNumber がありません",
            source="edgar",
            endpoint=EP_SUBMISSIONS,
        )
    keys = [
        "accessionNumber",
        "filingDate",
        "reportDate",
        "form",
        "primaryDocument",
        "primaryDocDescription",
        "items",
    ]
    n = len(recent["accessionNumber"])
    rows = []
    for i in range(n):
        rows.append({key: (recent.get(key) or [None] * n)[i] for key in keys})
    return rows


class EdgarConnector(HttpConnector):
    source = "edgar"

    required_payload_keys = {EP_COMPANYFACTS: ("facts",)}

    def __init__(self, *, user_agent: str | None = None, **kwargs: Any) -> None:
        self._user_agent_raw = user_agent
        super().__init__(**kwargs)

    def auth_headers(self) -> dict[str, str]:
        ua = self._user_agent_raw or self.config.secret(self.env)
        if not ua:
            # import と初期化は通す。fetch 前に require_credentials で落とす。
            return {"Accept-Encoding": "gzip, deflate"}
        return {"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}

    def require_credentials(self) -> None:
        validate_user_agent(self._user_agent_raw or self.config.secret(self.env))

    # ------------------------------------------------------------------
    def fetch(  # type: ignore[override]
        self,
        window: FetchWindow,
        *,
        ciks: list[str] | None = None,
        endpoint: str = EP_SUBMISSIONS,
        persist: bool = True,
        **kwargs: Any,
    ) -> Iterator[RawBatch]:
        self.require_credentials()

        if endpoint == EP_TICKERS:
            payload = self.http.get_json(
                "https://www.sec.gov/files/company_tickers.json", endpoint=EP_TICKERS
            )
            self._checkpoint.bump("api_calls")
            yield self.make_batch(
                endpoint=EP_TICKERS, as_of=window.end, payload=payload, persist=persist
            )
            return

        for cik in ciks or []:
            unit = f"{endpoint}:{cik}"
            if self._checkpoint.is_done(unit):
                continue
            urls = edgar_urls(cik, "0000000000-00-000000", "")
            url = urls.submissions_json if endpoint == EP_SUBMISSIONS else urls.companyfacts_json
            try:
                payload = self.http.get_json(url, endpoint=endpoint)
            except NotFoundError:
                self._checkpoint.mark_done(unit)
                self._checkpoint.bump("not_found")
                continue
            self._checkpoint.bump("api_calls")
            yield self.make_batch(
                endpoint=endpoint,
                as_of=window.end,
                payload=payload,
                request={"cik": cik},
                persist=persist,
            )
            self._checkpoint.mark_done(unit)

    # ------------------------------------------------------------------
    def normalize(self, batch: RawBatch) -> pd.DataFrame:
        if batch.endpoint == EP_SUBMISSIONS:
            return self._normalize_submissions(batch)
        if batch.endpoint == EP_COMPANYFACTS:
            return self._normalize_companyfacts(batch)
        if batch.endpoint == EP_TICKERS:
            return self._normalize_tickers(batch)
        raise SchemaDriftError(
            f"未知のエンドポイント: {batch.endpoint}", source=self.source, endpoint=batch.endpoint
        )

    def _normalize_submissions(self, batch: RawBatch) -> pd.DataFrame:
        payload = batch.payload or {}
        rows = parse_submissions(payload)
        if not rows:
            return tag_table(pd.DataFrame(), "documents")
        cik = str(payload.get("cik") or batch.request.get("cik") or "")
        ticker = _first_ticker(payload)
        records = []
        for row in rows:
            accession = str(row["accessionNumber"])
            form = str(row.get("form") or "")
            primary = str(row.get("primaryDocument") or "")
            urls = edgar_urls(cik, accession, primary)
            items = str(row.get("items") or "")
            if form == "8-K" and items and not any(
                item in items for item in EIGHT_K_ITEMS_OF_INTEREST
            ):
                # Item 2.02 / 5.02 以外の 8-K はメタデータのみで十分。
                pass
            records.append(
                {
                    "doc_id": f"edgar:{accession}",
                    "ticker": ticker,
                    "market": "US",
                    "source": self.source,
                    "form_code": form,
                    "doc_type": FORM_TO_DOC_TYPE.get(form, "other_disclosure"),
                    "title": row.get("primaryDocDescription") or form,
                    "period_end": _to_date(row.get("reportDate")),
                    "filed_at": pd.to_datetime(row.get("filingDate"), errors="coerce"),
                    "source_url": urls.primary_doc if primary else urls.filing_index,
                    "pdf_url": None,
                    "xbrl_url": urls.ixviewer,
                    "language": "en",
                    "is_amendment": form.endswith("/A"),
                    "should_download": form in FULL_TEXT_FORMS,
                    "items": items or None,
                    "ingested_at": now_utc(),
                }
            )
        df = pd.DataFrame(records)
        df = df[df["filed_at"].notna()]
        return tag_table(df.reset_index(drop=True), "documents")

    def _normalize_companyfacts(self, batch: RawBatch) -> pd.DataFrame:
        self.assert_payload_shape(batch)
        payload = batch.payload
        facts = (payload.get("facts") or {}).get("us-gaap") or {}
        cik = str(payload.get("cik") or batch.request.get("cik") or "")
        ticker = str(payload.get("entityName") or batch.request.get("ticker") or "")
        if batch.request.get("ticker"):
            ticker = str(batch.request["ticker"])

        # (accession, period_end, fiscal_period) をキーに横持ちへ組み立てる。
        collected: dict[tuple[str, str, str], dict[str, Any]] = {}
        for column, tags in USGAAP_TAGS.items():
            for tag in tags:
                entry = facts.get(tag)
                if not entry:
                    continue
                for unit_points in (entry.get("units") or {}).values():
                    for point in unit_points:
                        accn = str(point.get("accn") or "")
                        end = str(point.get("end") or "")
                        fp = str(point.get("fp") or "FY")
                        filed = point.get("filed")
                        if not (accn and end and filed):
                            continue
                        key = (accn, end, fp)
                        record = collected.setdefault(
                            key,
                            {
                                "ticker": ticker,
                                "market": "US",
                                "period_end": _to_date(end),
                                # `filed` を PIT の基準にする。`end` ではない。
                                "filed_at": _to_date(filed),
                                "fiscal_year": point.get("fy"),
                                "fiscal_period": fp,
                                "period_type": "annual" if fp == "FY" else "quarter",
                                "accession": accn,
                                "form": point.get("form"),
                                "cik": cik,
                            },
                        )
                        record.setdefault(column, point.get("val"))
                break  # 最初に見つかったタグのみを使う

        if not collected:
            return tag_table(pd.DataFrame(), "financials")

        df = pd.DataFrame(list(collected.values()))
        df["accounting_standard"] = "USGAAP"
        df["currency"] = "USD"
        df["source"] = self.source
        df["ingested_at"] = now_utc()
        df["fiscal_year"] = pd.to_numeric(df.get("fiscal_year"), errors="coerce").astype("Int64")
        for column in USGAAP_TAGS:
            if column not in df.columns:
                df[column] = pd.NA
            df[column] = pd.to_numeric(df[column], errors="coerce")
        df = df[df["filed_at"].notna() & df["period_end"].notna()]
        return tag_table(df.reset_index(drop=True), "financials")

    def _normalize_tickers(self, batch: RawBatch) -> pd.DataFrame:
        payload = batch.payload or {}
        rows = list(payload.values()) if isinstance(payload, dict) else list(payload)
        if not rows:
            return tag_table(pd.DataFrame(), "securities")
        raw = pd.DataFrame(rows)
        df = pd.DataFrame(
            {
                "ticker": raw.get("ticker").astype(str),
                "market": "US",
                "name_local": raw.get("title"),
                "name_en": raw.get("title"),
                # 10桁ゼロ埋め文字列で保持する（docs/03-data-model.md §2.1）。
                "cik": raw.get("cik_str").astype(str).str.zfill(10),
                "currency": "USD",
                "valid_from": batch.as_of,
                "is_active": True,
                "ingested_at": now_utc(),
            }
        )
        return tag_table(df, "securities")

    def checkpoint(self) -> Checkpoint:
        return self._checkpoint


def _first_ticker(payload: dict[str, Any]) -> str | None:
    tickers = payload.get("tickers") or []
    return str(tickers[0]) if tickers else None


def _to_date(value: Any) -> date | None:
    if value is None:
        return None
    ts = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(ts) else ts.date()
