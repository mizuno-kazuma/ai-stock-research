"""決算資料（docs/09-api-spec.md §2.5）。"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response

from packages.core.config import get_settings
from packages.core.llm.errors import CostCapExceeded, KillSwitchActive
from packages.core.storage import issuer_key
from packages.schemas.common import Envelope
from packages.schemas.documents import (
    Document,
    DocumentChunkList,
    DocumentList,
    DocumentSummary,
    DocumentSummaryRequest,
)
from services.agent.wiring import llm_keys_configured
from services.api.deps import AppState, User, get_app_state, require_user, spent_today_usd
from services.api.envelope import wrap
from services.api.errors import cost_cap_exceeded, not_found, upstream_unavailable
from services.api.mapping import document_summary_from_row, documents_from_storage, map_doc_type
from services.api.runtime import generate_document_summary, load_document_chunks
from services.api.util import as_date, resolve_market

router = APIRouter(tags=["documents"])


def _all_docs(state: AppState) -> list[Document]:
    rows = state.duck.get_documents(limit=500)
    if rows:
        return documents_from_storage(state.duck, rows)
    if not state.is_seed_data:
        return []
    return documents_from_storage(state.duck, state.payload.get("filings") or [])


def _find_doc(state: AppState, doc_id: str) -> Document | None:
    row = state.duck.get_document(doc_id)
    if row:
        has = state.duck.get_document_summary(doc_id) is not None
        found = documents_from_storage(state.duck, [row], has_summary=has)
        return found[0] if found else None
    if not state.is_seed_data:
        return None
    for item in state.payload.get("filings") or []:
        if item.get("doc_id") == doc_id:
            found = documents_from_storage(
                state.duck, [item], has_summary=bool(item.get("has_summary"))
            )
            return found[0] if found else None
    return None


@router.get("/documents", response_model=Envelope[DocumentList])
def list_documents(
    market: str | None = None,
    doc_type: str | None = None,
    filed_from: dt.date | None = None,
    filed_to: dt.date | None = None,
    held_only: bool = False,
    watchlist_only: bool = False,
    has_summary: bool | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[DocumentList]:
    if market:
        market = resolve_market(market)
    mapped = map_doc_type(doc_type) if doc_type else None
    items = _all_docs(state)
    held = {issuer_key(p.market, p.ticker) for p in state.sqlite.get_positions()}
    watch = {issuer_key(w.market, w.ticker) for w in state.sqlite.get_watchlist()}
    filtered: list[Document] = []
    for doc in items:
        if market and doc.market != market:
            continue
        if mapped and doc.doc_type != mapped:
            continue
        filed = doc.filed_at.date() if isinstance(doc.filed_at, dt.datetime) else as_date(doc.filed_at)
        if filed_from and filed and filed < filed_from:
            continue
        if filed_to and filed and filed > filed_to:
            continue
        key = issuer_key(doc.market, doc.ticker)
        if held_only and key not in held:
            continue
        if watchlist_only and key not in watch:
            continue
        if has_summary is not None and doc.has_summary != has_summary:
            continue
        filtered.append(doc)
    page = filtered[offset : offset + limit]
    return wrap(state, DocumentList(items=page, total=len(filtered), limit=limit, offset=offset))


@router.get("/documents/{doc_id}", response_model=Envelope[Document])
def get_document(
    doc_id: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[Document]:
    doc = _find_doc(state, doc_id)
    if doc is None:
        raise not_found(f"資料 {doc_id} は存在しません。")
    return wrap(state, doc)


@router.get("/documents/{doc_id}/file")
def get_document_file(
    doc_id: str,
    disposition: str = Query(default="inline"),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Response:
    doc = _find_doc(state, doc_id)
    if doc is None:
        raise not_found(f"資料 {doc_id} は存在しません。")
    row = state.duck.get_document(doc_id) or {}
    blob = row.get("blob_path")
    if blob:
        path = Path(blob)
        if path.is_file():
            return FileResponse(
                path,
                media_type="application/pdf",
                filename=path.name,
                headers={
                    "Cache-Control": "max-age=31536000, immutable",
                    "Content-Disposition": f'{disposition}; filename="{path.name}"',
                },
            )
    raise not_found("ローカルに PDF がありません。source_url を使ってください。")


@router.get("/documents/{doc_id}/summary", response_model=Envelope[DocumentSummary])
def get_summary(
    doc_id: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[DocumentSummary]:
    row = state.duck.get_document_summary(doc_id)
    if row:
        return wrap(state, document_summary_from_row(row))
    seed = state.payload.get("filing_summary") or {}
    if seed.get("doc_id") == doc_id:
        payload = dict(seed)
        payload.setdefault("summary_ja", seed.get("headline_ja") or "")
        payload.setdefault("model_id", seed.get("model"))
        payload.setdefault("computed_at", seed.get("generated_at"))
        return wrap(state, document_summary_from_row(payload))
    raise not_found(f"資料 {doc_id} の要約はありません。")


@router.post("/documents/{doc_id}/summary", response_model=Envelope[DocumentSummary])
def post_summary(
    doc_id: str,
    body: DocumentSummaryRequest | None = None,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[DocumentSummary]:
    doc = _find_doc(state, doc_id)
    if doc is None:
        raise not_found(f"資料 {doc_id} は存在しません。")
    force = bool(body and body.force_regenerate)
    existing = None
    try:
        existing = get_summary(doc_id, _user, state)
    except Exception:
        existing = None
    if existing is not None and not force:
        return existing
    settings = get_settings()
    spent = spent_today_usd(state)
    cap = float(state.sqlite.get_setting("llm.daily_cap_usd", settings.llm_daily_cap_usd))
    kill = bool(state.sqlite.get_setting("llm.kill_switch", False) or settings.llm_kill_switch)
    if kill or spent >= cap:
        tomorrow = (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).replace(
            hour=15, minute=0, second=0, microsecond=0
        )
        raise cost_cap_exceeded(
            spent_today_usd=spent,
            daily_cap_usd=cap,
            resets_at=tomorrow,
            instance=f"/api/v1/documents/{doc_id}/summary",
        )
    if not llm_keys_configured(settings):
        raise upstream_unavailable(
            "オンデマンド要約は LLM が未接続のため生成できません。キャッシュ済み要約を GET してください。",
            instance=f"/api/v1/documents/{doc_id}/summary",
        )
    try:
        summary = generate_document_summary(state, doc_id=doc_id, doc=doc)
    except (CostCapExceeded, KillSwitchActive):
        tomorrow = (dt.datetime.now(dt.UTC) + dt.timedelta(days=1)).replace(
            hour=15, minute=0, second=0, microsecond=0
        )
        raise cost_cap_exceeded(
            spent_today_usd=spent,
            daily_cap_usd=cap,
            resets_at=tomorrow,
            instance=f"/api/v1/documents/{doc_id}/summary",
        ) from None
    except Exception:
        raise upstream_unavailable(
            "オンデマンド要約は LLM が未接続のため生成できません。キャッシュ済み要約を GET してください。",
            instance=f"/api/v1/documents/{doc_id}/summary",
        ) from None
    return wrap(state, summary)


@router.get("/documents/{doc_id}/chunks", response_model=Envelope[DocumentChunkList])
def get_chunks(
    doc_id: str,
    section: str | None = None,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[DocumentChunkList]:
    if _find_doc(state, doc_id) is None:
        raise not_found(f"資料 {doc_id} は存在しません。")
    return wrap(state, load_document_chunks(state, doc_id, section=section))
