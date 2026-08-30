"""ハイブリッド検索と Reciprocal Rank Fusion（docs/07-llm-rag.md §4）。

PIT 制約 (`as_of`) を検索にも適用する。当時知り得なかった資料を検索してはいけない。
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Any

from packages.core.interfaces.storage import KeywordSearch, SearchHit, VectorStore
from packages.core.storage.vector_store import DocChunk, chunk_id_for

logger = logging.getLogger(__name__)

# 見出し優先のセクション正規化（docs/07-llm-rag.md §4.2）。
SECTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"事業等のリスク|Item\s*1A|Risk Factors", re.IGNORECASE), "risk_factors"),
    (
        re.compile(
            r"経営者による財政状態|Item\s*7|MD&A|Management'?s Discussion",
            re.IGNORECASE,
        ),
        "mdna",
    ),
    (re.compile(r"業績等の概要|経営成績|Results of Operations", re.IGNORECASE), "results"),
    (re.compile(r"今後の見通し|次期の業績予想|Outlook|Guidance", re.IGNORECASE), "outlook"),
    (re.compile(r"財務諸表|Financial Statements", re.IGNORECASE), "financials"),
    (
        re.compile(r"重要な会計上の見積り|Critical Accounting", re.IGNORECASE),
        "accounting_estimates",
    ),
)

HEADING_LINE = re.compile(
    r"^(?:#{1,3}\s+|[第]?[0-9一二三四五六七八九十]+[章節条項]\s*|"
    r"Item\s+[0-9]+[A-Z]?\.?\s+)",
    re.IGNORECASE,
)


def reciprocal_rank_fusion(
    *rankings: Sequence[SearchHit], k: int = 60
) -> list[SearchHit]:
    scores: dict[str, float] = defaultdict(float)
    by_id: dict[str, SearchHit] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking, start=1):
            scores[hit.chunk_id] += 1.0 / (k + rank)
            by_id[hit.chunk_id] = hit
    ordered = sorted(scores, key=lambda cid: -scores[cid])
    out = []
    for cid in ordered:
        hit = by_id[cid]
        out.append(
            SearchHit(
                chunk_id=hit.chunk_id,
                doc_id=hit.doc_id,
                text=hit.text,
                score=scores[cid],
                ticker=hit.ticker,
                market=hit.market,
                doc_type=hit.doc_type,
                filed_at=hit.filed_at,
                section=hit.section,
                page_from=hit.page_from,
                page_to=hit.page_to,
                title=hit.title,
            )
        )
    return out


def retrieve(
    query: str,
    *,
    ticker: str,
    market: str,
    k: int = 8,
    filed_after: date | None = None,
    doc_types: list[str] | None = None,
    sections: list[str] | None = None,
    as_of: date | None = None,
    embed: Callable[[str], list[float]] | None = None,
    vector_store: VectorStore | None = None,
    keyword_search: KeywordSearch | None = None,
) -> list[SearchHit]:
    """ベクトル検索 + キーワード検索を統合する。両方無ければ空。"""
    vec_hits: list[SearchHit] = []
    kw_hits: list[SearchHit] = []
    if vector_store is not None and embed is not None:
        try:
            q_vec = embed(query)
            filters: dict[str, Any] = {"ticker": ticker, "market": market}
            if as_of is not None:
                filters["filed_at"] = {"$lte": as_of}
            if doc_types:
                filters["doc_type"] = {"$in": doc_types}
            if sections:
                filters["section"] = {"$in": sections}
            raw_vec = vector_store.search(q_vec, k=k * 3, filters=filters)
            vec_hits = [_as_search_hit(h) for h in raw_vec]
        except Exception:
            logger.warning("ベクトル検索に失敗したためキーワード検索のみ使います", exc_info=True)
            vec_hits = []
    if keyword_search is not None:
        kw_hits = [
            _as_search_hit(h)
            for h in keyword_search.search_text(
                query, k=k * 3, ticker=ticker, market=market, as_of=as_of, doc_types=doc_types
            )
        ]
    merged = reciprocal_rank_fusion(vec_hits, kw_hits) if (vec_hits or kw_hits) else []
    filtered = []
    for hit in merged:
        if as_of is not None and hit.filed_at is not None and hit.filed_at.date() > as_of:
            continue
        if filed_after is not None and hit.filed_at is not None and hit.filed_at.date() < filed_after:
            continue
        filtered.append(hit)
        if len(filtered) >= k:
            break
    return filtered


def estimate_tokens(text: str) -> int:
    """日本語混在テキストの粗いトークン見積もり（2文字≒1トークン）。"""
    return max(1, (len(text) + 1) // 2)


def detect_section(text: str) -> str:
    """見出しから正規化セクション名を返す。失敗時は `other`。"""
    sample = (text or "")[:800]
    for pattern, name in SECTION_PATTERNS:
        if pattern.search(sample):
            return name
    return "other"


def chunk_document_text(
    text: str,
    *,
    max_tokens: int = 1000,
    overlap_tokens: int = 150,
) -> list[tuple[str, str]]:
    """本文を見出し優先 → 段落 → 文で分割する（docs/07-llm-rag.md §4.2）。

    戻り値は `(section, chunk_text)`。表（`|` を含む連続行）は分割しない。
    """
    body = (text or "").strip()
    if not body:
        return []
    blocks = _split_blocks(body)
    packed: list[tuple[str, str]] = []
    current_section = "other"
    current: list[str] = []
    current_tokens = 0

    def flush(*, final: bool = False) -> None:
        nonlocal current, current_tokens
        if not current:
            return
        packed.append((current_section, "\n\n".join(current).strip()))
        if final:
            current = []
            current_tokens = 0
            return
        overlap: list[str] = []
        acc = 0
        for prev in reversed(current):
            acc += estimate_tokens(prev)
            overlap.insert(0, prev)
            if acc >= overlap_tokens:
                break
        current = overlap
        current_tokens = sum(estimate_tokens(x) for x in current)

    for block in blocks:
        heading = _heading_section(block)
        if heading is not None:
            flush()
            current = []
            current_tokens = 0
            current_section = heading
            continue
        pieces = _split_oversize(block, max_tokens)
        for piece in pieces:
            tokens = estimate_tokens(piece)
            if current and current_tokens + tokens > max_tokens:
                flush()
            current.append(piece)
            current_tokens += tokens
    flush(final=True)
    return [(sec, chunk) for sec, chunk in packed if chunk]


def index_document(
    *,
    doc_id: str,
    text: str,
    market: str,
    ticker: str | None = None,
    doc_type: str | None = None,
    filed_at: datetime | None = None,
    embed: Callable[[str], list[float]],
    vector_store: VectorStore,
    embedding_model: str = "unknown",
    page_from: int | None = None,
    page_to: int | None = None,
) -> int:
    """1資料をチャンク化してベクトルストアへ upsert する。失敗時は 0。"""
    body = (text or "").strip()
    if not body:
        return 0
    try:
        vector_store.delete_by_doc(doc_id)
    except Exception:
        logger.debug("既存チャンクの削除をスキップ: %s", doc_id)
    chunks: list[DocChunk] = []
    for index, (section, chunk_text) in enumerate(chunk_document_text(body)):
        try:
            embedding = embed(chunk_text)
        except Exception:
            logger.warning("埋め込みに失敗したためこのチャンクを飛ばします: %s#%s", doc_id, index)
            continue
        if not embedding:
            continue
        chunks.append(
            DocChunk(
                chunk_id=chunk_id_for(doc_id, index),
                doc_id=doc_id,
                text=chunk_text,
                embedding=list(embedding),
                market=market,
                ticker=ticker,
                doc_type=doc_type,
                filed_at=filed_at,
                page_from=page_from if page_from is not None else 1,
                page_to=page_to if page_to is not None else 1,
                section=section,
                token_count=estimate_tokens(chunk_text),
                embedding_model=embedding_model,
                embedding_version="v1",
            )
        )
    if not chunks:
        return 0
    return int(vector_store.upsert(chunks))


def _as_search_hit(hit: Any) -> SearchHit:
    if isinstance(hit, SearchHit):
        return hit
    filed = getattr(hit, "filed_at", None)
    return SearchHit(
        chunk_id=str(getattr(hit, "chunk_id", "") or ""),
        doc_id=str(getattr(hit, "doc_id", "") or ""),
        text=str(getattr(hit, "text", "") or ""),
        score=float(getattr(hit, "score", 0.0) or 0.0),
        ticker=getattr(hit, "ticker", None),
        market=getattr(hit, "market", None),
        doc_type=getattr(hit, "doc_type", None),
        filed_at=filed if isinstance(filed, datetime) else None,
        section=getattr(hit, "section", None),
        page_from=getattr(hit, "page_from", None),
        page_to=getattr(hit, "page_to", None),
        title=getattr(hit, "title", None),
    )


def _heading_section(block: str) -> str | None:
    """単独行の見出しだけをセクション境界にする。本文の冒頭語では切らない。"""
    first = block.strip().splitlines()[0] if block.strip() else ""
    if not first or len(first) > 40 or "。" in first:
        return None
    if not HEADING_LINE.search(first) and not any(p.search(first) for p, _ in SECTION_PATTERNS):
        return None
    return detect_section(first)


def _split_blocks(text: str) -> list[str]:
    lines = text.replace("\r\n", "\n").split("\n")
    blocks: list[str] = []
    buf: list[str] = []
    in_table = False

    def flush_buf() -> None:
        nonlocal buf
        joined = "\n".join(buf).strip()
        if joined:
            blocks.append(joined)
        buf = []

    for line in lines:
        table_line = "|" in line or bool(re.match(r"^\s*[-+]{3,}", line))
        if table_line:
            if not in_table and buf:
                flush_buf()
            in_table = True
            buf.append(line)
            continue
        if in_table:
            flush_buf()
            in_table = False
        if not line.strip():
            flush_buf()
            continue
        buf.append(line)
    flush_buf()
    return blocks


def _split_oversize(block: str, max_tokens: int) -> list[str]:
    if estimate_tokens(block) <= max_tokens or "|" in block:
        return [block]
    sentences = re.split(r"(?<=。)", block)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return [block]
    out: list[str] = []
    current = ""
    for sent in sentences:
        candidate = f"{current}{sent}" if current else sent
        if current and estimate_tokens(candidate) > max_tokens:
            out.append(current)
            current = sent
        else:
            current = candidate
    if current:
        out.append(current)
    return out or [block]
