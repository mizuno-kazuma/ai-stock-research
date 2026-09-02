"""EDINET API v2（日本の開示資料）。

docs/02-data-ingestion.md §5、docs/06-filings-access.md §3。

- 認証は `Ocp-Apim-Subscription-Key` ヘッダ（`Subscription-Key` では 401 になる）
- 日次バッチで前営業日の `documents.json?date=...&type=2` を1回取得する
- 取得対象は `docTypeCode` で絞る
- PDF（`type=2`）を優先ダウンロードする（Gemini が PDF をネイティブ入力できるため）
- ファイル名は `docID` ベースにし、日本語タイトルはDBカラムに持つ
"""

from __future__ import annotations

import logging
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
from packages.core.connectors.edinet_urls import edinet_viewer_url
from packages.core.connectors.errors import (
    AuthError,
    ConfigurationError,
    NotFoundError,
    SchemaDriftError,
    TransientError,
)
from packages.core.connectors.paths import blob_path, document_native_id, existing_document_blob

logger = logging.getLogger(__name__)

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

        `[要検証]` `packages.core.connectors.edinet_urls.edinet_viewer_url` を正とする。
        `?S100=` 形式は規定外操作（WZEK0130）になる。
        """
        return edinet_viewer_url(doc_id)

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
                payload = self._list_documents(day, list_type="2")
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

    def _list_documents(self, day: date, *, list_type: str) -> dict[str, Any]:
        """書類一覧。type=2 が空なら type=1（メタデータのみ）にフォールバックする。"""
        payload = self._get_documents_json(day, list_type)
        if _result_rows(payload):
            return payload
        if list_type != "1":
            fallback = self._get_documents_json(day, "1")
            if _result_rows(fallback):
                return fallback
        return payload

    def _get_documents_json(self, day: date, list_type: str) -> dict[str, Any]:
        payload = self.http.get_json(
            self.documents_url(),
            params={"date": day.isoformat(), "type": list_type},
            endpoint=EP_DOCUMENTS,
        )
        if not isinstance(payload, dict):
            raise SchemaDriftError(
                f"edinet/documents: dict を期待しましたが {type(payload).__name__} でした",
                source=self.source,
                endpoint=EP_DOCUMENTS,
            )
        apim_status = _apim_status(payload)
        if apim_status in {"401", "403"}:
            message = str(payload.get("message") or "").strip()
            raise AuthError(
                f"edinet: 認証に失敗しました（StatusCode={apim_status}）。"
                "リトライせず中断します。APIキーと権限を確認してください。"
                + (f" {message}" if message else "")
            )
        if apim_status is not None and apim_status not in {"200", "201"}:
            message = str(payload.get("message") or "").strip()
            raise TransientError(
                f"edinet: date={day.isoformat()} type={list_type} "
                f"StatusCode={apim_status} {message}".strip()
            )
        meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        status = str(meta.get("status") or "200")
        if status not in {"200", "201"}:
            message = meta.get("message") or ""
            raise TransientError(
                f"edinet: date={day.isoformat()} type={list_type} "
                f"metadata.status={status} {message}".strip()
            )
        return payload

    def fetch_document_blob(self, doc_id: str, *, kind: str = "pdf") -> tuple[bytes, str] | None:
        """PDF / XBRL を取得して Raw層の blobs に保存する。

        既に保存済みなら再ダウンロードしない（docs §5.3 の 5.）。
        HTTP は native `docID`、ファイル名も native ID で揃える。
        """
        native = document_native_id(doc_id)
        canonical = doc_id if ":" in str(doc_id) else f"{self.source}:{doc_id}"
        ext = {"pdf": "pdf", "xbrl": "zip", "csv": "zip"}[kind]
        existing = existing_document_blob(
            data_dir=self.data_dir, source=self.source, doc_id=canonical, ext=ext
        )
        if existing is not None:
            return None
        self.require_credentials()
        try:
            content = self.http.get_bytes(self.download_url(native, kind), endpoint=EP_DOCUMENT_FILE)
        except NotFoundError:
            return None
        path = self.raw.write_blob(source=self.source, doc_id=native, content=content, ext=ext)
        self._checkpoint.bump("blobs_downloaded")
        return content, str(path)

    def persist_document_blobs(self, frame: pd.DataFrame) -> int:
        """`should_download` の PDF を Raw に保存し `blob_path` を埋める。

        大量保有などメタデータのみの書類は対象外。1件の 404 で全体は止めない。
        """
        if frame.empty or "should_download" not in frame.columns:
            return 0
        mask = frame["should_download"].fillna(False).astype(bool)
        stored = 0
        updates: list[dict[str, Any]] = []
        for rec in frame.loc[mask].to_dict(orient="records"):
            doc_id = str(rec.get("doc_id") or "")
            native = document_native_id(doc_id)
            if not native:
                continue
            try:
                self.fetch_document_blob(native, kind="pdf")
            except (AuthError, ConfigurationError):
                raise
            except NotFoundError:
                continue
            except Exception:
                logger.exception("EDINET PDF の取得に失敗しました: %s", native)
                continue
            path = blob_path(self.data_dir, source=self.source, doc_id=native, ext="pdf")
            if not path.is_file():
                continue
            updates.append({**rec, "blob_path": str(path)})
            stored += 1
        if updates and self.warehouse is not None:
            self.warehouse.upsert_documents(updates)
        return stored

    # ------------------------------------------------------------------
    def normalize(self, batch: RawBatch) -> pd.DataFrame:
        self.assert_payload_shape(batch)
        payload = batch.payload if isinstance(batch.payload, dict) else {}
        results = _result_rows(payload)
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
        titles = raw["docDescription"] if "docDescription" in raw.columns else pd.Series([None] * len(raw))
        filer = raw["filerName"] if "filerName" in raw.columns else pd.Series([None] * len(raw))
        period_end = (
            pd.to_datetime(raw["periodEnd"], errors="coerce").dt.date
            if "periodEnd" in raw.columns
            else pd.Series([None] * len(raw))
        )
        df = pd.DataFrame(
            {
                "doc_id": "edinet:" + raw["docID"].astype(str),
                "ticker": _normalize_sec_code(raw.get("secCode")),
                "market": "JP",
                "name_local": filer,
                "source": self.source,
                "form_code": doc_type_code,
                "doc_type": doc_type_code.map(lambda c: DOC_TYPE_MAP.get(c, "other_disclosure")),
                # 日本語タイトルは原文のまま保持する。ファイル名には使わない。
                "title": titles,
                "edinet_code": raw.get("edinetCode"),
                "period_end": period_end,
                "filed_at": pd.to_datetime(raw.get("submitDateTime"), errors="coerce")
                if "submitDateTime" in raw.columns
                else pd.Series([pd.NaT] * len(raw)),
                "language": "ja",
                "is_amendment": doc_type_code.isin(AMENDMENT_CODES),
                "ingested_at": now_utc(),
            }
        )
        missing_filed = df["filed_at"].isna()
        if missing_filed.any():
            df.loc[missing_filed, "filed_at"] = pd.Timestamp(batch.as_of)
        df["title"] = df["title"].fillna("").astype(str).str.strip()
        df.loc[df["title"] == "", "title"] = df.loc[df["title"] == "", "doc_id"]
        names = df["name_local"].astype("string").str.strip()
        df["name_local"] = names.mask(names.isin(["", "<NA>"]))
        df["source_url"] = raw["docID"].astype(str).map(self.viewer_url)
        df["pdf_url"] = raw["docID"].astype(str).map(lambda d: self.download_url(d, "pdf"))
        df["xbrl_url"] = raw["docID"].astype(str).map(lambda d: self.download_url(d, "xbrl"))
        df["should_download"] = doc_type_code.isin(FULL_DOWNLOAD_TYPES)
        df["disclosed_at"] = df["filed_at"]
        return tag_table(df.reset_index(drop=True), "documents")

    def checkpoint(self) -> Checkpoint:
        return self._checkpoint


def _apim_status(payload: dict[str, Any]) -> str | None:
    """Azure APIM は HTTP 200 のまま `{StatusCode, message}` だけ返すことがある。

    `metadata` がある通常レスポンスは対象外。ヘッダ名を `Subscription-Key` に
    すると 401 になり、空の results として成功扱いになっていた。
    """
    if isinstance(payload.get("metadata"), dict):
        return None
    raw = payload.get("StatusCode")
    if raw is None:
        raw = payload.get("statusCode")
    if raw is None:
        return None
    return str(raw)


def _result_rows(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        return []
    for key in ("results", "Results"):
        rows = payload.get(key)
        if isinstance(rows, list) and rows:
            return rows
    return []


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
