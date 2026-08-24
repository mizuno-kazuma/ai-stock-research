"""ハイブリッド検索と Reciprocal Rank Fusion（docs/07-llm-rag.md §4）。

PIT 制約 (`as_of`) を検索にも適用する。当時知り得なかった資料を検索してはいけない。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import date
from typing import Any

from packages.core.interfaces.storage import KeywordSearch, SearchHit, VectorStore


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
        q_vec = embed(query)
        filters: dict[str, Any] = {"ticker": ticker, "market": market}
        if as_of is not None:
            filters["filed_at"] = {"$lte": as_of}
        if doc_types:
            filters["doc_type"] = {"$in": doc_types}
        if sections:
            filters["section"] = {"$in": sections}
        vec_hits = vector_store.search(q_vec, k=k * 3, filters=filters)
    if keyword_search is not None:
        kw_hits = keyword_search.search_text(
            query, k=k * 3, ticker=ticker, market=market, as_of=as_of, doc_types=doc_types
        )
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
