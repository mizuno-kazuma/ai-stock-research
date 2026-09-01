"""開示資料のローカル PDF 配信と、無いときの公式サイトへの縮退。

docs/06-filings-access.md §3.3 / §9。UI は常に `/documents/{id}/file` を開き、
ローカルコピーが無ければ `source_url`（EDINET 閲覧画面など）へ送る。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi.responses import FileResponse, RedirectResponse, Response

from packages.core.connectors.errors import (
    AuthError,
    ConfigurationError,
    NotFoundError,
    SourceDisabledError,
)
from packages.core.connectors.paths import document_native_id, existing_document_blob
from packages.schemas.documents import Document
from services.api.deps import AppState

logger = logging.getLogger(__name__)


def resolve_local_pdf(state: AppState, doc: Document, row: dict[str, Any] | None = None) -> Path | None:
    stored = None if row is None else row.get("blob_path")
    return existing_document_blob(
        data_dir=state.settings.data_dir,
        source=str(doc.source or "edinet"),
        doc_id=doc.doc_id,
        stored_path=str(stored) if stored else None,
        ext="pdf",
    )


def fetch_and_store_pdf(state: AppState, doc: Document, row: dict[str, Any] | None = None) -> Path | None:
    """未保存なら EDINET から PDF を取り、保存できればパスを返す。失敗は None。"""
    if str(doc.source) != "edinet":
        return None
    existing = resolve_local_pdf(state, doc, row)
    if existing is not None:
        return existing
    native = document_native_id(doc.doc_id)
    if not native:
        return None
    try:
        from packages.core.connectors.edinet import EdinetConnector
    except ImportError:
        return None
    key = getattr(state.settings, "edinet_subscription_key", None)
    secret = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key or "")
    connector = None
    try:
        connector = EdinetConnector(
            data_dir=state.settings.data_dir,
            warehouse=state.duck,
            env={"EDINET_SUBSCRIPTION_KEY": secret or ""},
            require_enabled=True,
        )
        connector.fetch_document_blob(native, kind="pdf")
    except (AuthError, ConfigurationError, SourceDisabledError):
        logger.info("EDINET PDF のオンデマンド取得をスキップしました: %s", doc.doc_id)
        return None
    except NotFoundError:
        return None
    except Exception:
        logger.exception("EDINET PDF のオンデマンド取得に失敗しました: %s", doc.doc_id)
        return None
    finally:
        if connector is not None:
            close = getattr(connector, "close", None)
            if callable(close):
                close()
    found = resolve_local_pdf(state, doc, row)
    if found is None:
        return None
    if row is not None:
        try:
            state.duck.upsert_documents([{**row, "blob_path": str(found)}])
        except Exception:
            logger.info("blob_path の保存をスキップしました: %s", doc.doc_id)
    return found


def document_file_response(
    state: AppState,
    doc: Document,
    row: dict[str, Any] | None,
    *,
    disposition: str = "inline",
) -> Response:
    path = resolve_local_pdf(state, doc, row)
    if path is None:
        path = fetch_and_store_pdf(state, doc, row)
    if path is not None:
        filename = path.name
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=filename,
            headers={
                "Cache-Control": "max-age=31536000, immutable",
                "Content-Disposition": f'{disposition}; filename="{filename}"',
            },
        )
    if doc.source_url:
        return RedirectResponse(url=doc.source_url, status_code=302)
    from services.api.errors import not_found

    raise not_found("ローカルに PDF がなく、公式サイトの URL もありません。")
