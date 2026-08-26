"""EDINET API v2（日本の開示資料）。

docs/02-data-ingestion.md §5、docs/06-filings-access.md §3。

- 認証は `Subscription-Key` ヘッダ `[要検証]`
- 日次バッチで前営業日の `documents.json?date=...&type=2` を1回取得する
- 取得対象は `docTypeCode` で絞る
- PDF（`type=2`）を優先ダウンロードする（Gemini が PDF をネイティブ入力できるため）
- ファイル名は `docID` ベースにし、日本語タイトルはDBカラムに持つ
"""

from __future__ import annotations

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
from packages.core.connectors.errors import ConfigurationError, NotFoundError, SchemaDriftError

EP_DOCUMENTS = "documents"
EP_DOCUMENT_FILE = "document_file"

# `[要検証]` type パラメータの値と意味は公式仕様書で確認する。
DOWNLOAD_TYPE = {"xbrl": 1, "pdf": 2, "csv": 5}

# `[要検証]` docTypeCode → doc_type（docs/03-data-model.md §2.5 の値域）
DOC_TYPE_MAP: dict[str, str] = {
    "120": "annual_report",
    "130": "annual_report",  # 訂正有価証券報告書
    "140": "quarterly_report",
    "150": "quarterly_report",  # 訂正四半期報告書
    "160": "semiannual_report",
    "170": "semiannual_report",
    "180": "current_report",  # 臨時報告書
    "190": "current_report",
    "350": "large_holding",
    "360": "large_holding",
}
# 全文（PDF + XBRL）を取得する対象。それ以外はメタデータのみ。
FULL_DOWNLOAD_TYPES = frozenset({"120", "130", "140", "160"})
AMENDMENT_CODES = frozenset({"130", "150", "170", "190", "360"})


class EdinetConnector(HttpConnector):
    source = "edinet"

    required_payload_keys = {EP_DOCUMENTS: ()}

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

    # ------------------------------------------------------------------
    def documents_url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/documents.json"

    def download_url(self, doc_id: str, kind: str = "pdf") -> str:
        """API 経由のダウンロードURL。ヘッダ認証が必要なのでUIから直接開けない。"""
        return f"{self.config.base_url.rstrip('/')}/documents/{doc_id}?type={DOWNLOAD_TYPE[kind]}"

    @staticmethod
    def viewer_url(doc_id: str) -> str:
        """ブラウザで直接開ける閲覧画面URL。

        `[要検証]` EDINET の閲覧画面URLは過去に何度か変わっている。
        変更時にここ1箇所を直せば済むようにしている。
        """
        return f"https://disclosure2.edinet-fsa.go.jp/WZEK0040.aspx?S100={doc_id}"

    def require_credentials(self) -> None:
        if not self.auth_headers():
            raise ConfigurationError("EDINET_SUBSCRIPTION_KEY が設定されていません")

    # ------------------------------------------------------------------
    def fetch(  # type: ignore[override]
        self,
        window: FetchWindow,
        *,
        persist: bool = True,
        **kwargs: Any,
    ) -> Iterator[RawBatch]:
        self.require_credentials()
        for day in window.business_days():
            unit = f"{EP_DOCUMENTS}:{day.isoformat()}"
            if self._checkpoint.is_done(unit):
                continue
            params = {"date": day.isoformat(), "type": "2"}
            try:
                payload = self.http.get_json(
                    self.documents_url(), params=params, endpoint=EP_DOCUMENTS
                )
            except NotFoundError:
                self._checkpoint.mark_done(unit)
                continue
            self._checkpoint.bump("api_calls")
            yield self.make_batch(
                endpoint=EP_DOCUMENTS,
                as_of=day,
                payload=payload,
                request=params,
                persist=persist,
            )
            self._checkpoint.mark_done(unit)

    def fetch_document_blob(self, doc_id: str, *, kind: str = "pdf") -> tuple[bytes, str] | None:
        """PDF / XBRL を取得して Raw層の blobs に保存する。

        既に保存済みなら再ダウンロードしない（docs §5.3 の 5.）。
        """
        self.require_credentials()
        ext = {"pdf": "pdf", "xbrl": "zip", "csv": "zip"}[kind]
        if self.raw.blob_exists(source=self.source, doc_id=doc_id, ext=ext):
            return None
        try:
            content = self.http.get_bytes(self.download_url(doc_id, kind), endpoint=EP_DOCUMENT_FILE)
        except NotFoundError:
            return None
        path = self.raw.write_blob(source=self.source, doc_id=doc_id, content=content, ext=ext)
        self._checkpoint.bump("blobs_downloaded")
        return content, str(path)

    # ------------------------------------------------------------------
    def normalize(self, batch: RawBatch) -> pd.DataFrame:
        self.assert_payload_shape(batch)
        payload = batch.payload if isinstance(batch.payload, dict) else {}
        results = payload.get("results")
        if not results:
            return tag_table(pd.DataFrame(), "documents")

        raw = pd.DataFrame(results)
        if "docID" not in raw.columns:
            raise SchemaDriftError(
                "edinet/documents: docID がありません",
                source=self.source,
                endpoint=batch.endpoint,
            )

        doc_type_code = raw.get("docTypeCode", pd.Series([None] * len(raw))).astype(str)
        df = pd.DataFrame(
            {
                "doc_id": "edinet:" + raw["docID"].astype(str),
                "ticker": _normalize_sec_code(raw.get("secCode")),
                "market": "JP",
                "source": self.source,
                "form_code": doc_type_code,
                "doc_type": doc_type_code.map(lambda c: DOC_TYPE_MAP.get(c, "other_disclosure")),
                # 日本語タイトルは原文のまま保持する。ファイル名には使わない。
                "title": raw.get("docDescription"),
                "edinet_code": raw.get("edinetCode"),
                "period_end": pd.to_datetime(raw.get("periodEnd"), errors="coerce").dt.date,
                "filed_at": pd.to_datetime(raw.get("submitDateTime"), errors="coerce"),
                "language": "ja",
                "is_amendment": doc_type_code.isin(AMENDMENT_CODES),
                "ingested_at": now_utc(),
            }
        )
        df["source_url"] = raw["docID"].astype(str).map(self.viewer_url)
        df["pdf_url"] = raw["docID"].astype(str).map(lambda d: self.download_url(d, "pdf"))
        df["xbrl_url"] = raw["docID"].astype(str).map(lambda d: self.download_url(d, "xbrl"))
        df["should_download"] = doc_type_code.isin(FULL_DOWNLOAD_TYPES)
        df["disclosed_at"] = df["filed_at"]
        df = df[df["filed_at"].notna()]
        return tag_table(df.reset_index(drop=True), "documents")

    def checkpoint(self) -> Checkpoint:
        return self._checkpoint


def _normalize_sec_code(series: Any) -> pd.Series:
    """EDINET の secCode は5桁（末尾0）。4桁の証券コードへ寄せる。

    数値型にしない。`130A` のような英字を含むコードに対応するため。
    """
    if series is None:
        return pd.Series(dtype=object)
    values = pd.Series(series).astype(object)

    def convert(value: Any) -> str | None:
        if value is None or pd.isna(value):
            return None
        text = str(value).strip()
        if not text:
            return None
        if len(text) == 5 and text.endswith("0"):
            return text[:4]
        return text

    return values.map(convert)
