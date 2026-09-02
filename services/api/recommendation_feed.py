"""推奨タブの母集団（スコア済みユニバース + 推奨カード）。

docs/05-scoring-screening.md §7.8。Critic の却下は承認に書き換えない。
カードがない行でも会社名とスコアを必ず載せる。
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd

from packages.core.factors.screening import assign_reason_codes
from packages.core.storage import issuer_key, unique_by_issuer
from packages.schemas.recommendations import (
    MIN_VISIBLE_RECOMMENDATIONS,
    RecommendationCard,
    RecommendationFeedItem,
    RecommendationList,
)
from services.api.deps import AppState
from services.api.mapping import (
    display_company_name,
    recommendation_from_row,
    recommendation_from_seed,
    securities_by_issuer,
)
from services.api.util import as_date

UNIVERSE_FETCH_LIMIT = 5_000
HIGHLIGHT_COUNT = MIN_VISIBLE_RECOMMENDATIONS

_VERDICT_RANK = {"approved": 0, "revised": 1, None: 2, "rejected": 3}
_TIER_RANK = {"core": 0, "fill": 1, "score_only": 2}


@dataclass
class FeedQuery:
    market: str
    as_of: dt.date | None = None
    horizon: str | None = "H20"
    actions: list[str] = field(default_factory=list)
    convictions: list[str] = field(default_factory=list)
    critic_verdicts: list[str] = field(default_factory=list)
    sector: str | None = None
    min_score: float | None = None
    reason_codes: list[str] = field(default_factory=list)
    pred_sign: Literal["positive", "negative"] | None = None
    has_card: bool | None = None
    include_rejected: bool = True
    limit: int = 50
    offset: int = 0
    sort: str = "total_score"
    highlights: bool = False


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _score_value(item: RecommendationFeedItem) -> float:
    for raw in (item.total_score, item.quant_score):
        if raw is not None:
            return float(raw)
    return float("-inf")


def _display_tier(card: RecommendationCard | None) -> str:
    if card is None:
        return "score_only"
    codes = {str(c) for c in card.reason_codes}
    if "RANK_FILL" in codes:
        return "fill"
    return "core"


def _company_name(
    *,
    ticker: str,
    market: str,
    security: dict[str, Any] | None,
    score: dict[str, Any] | None,
    card: RecommendationCard | None,
) -> str:
    sec = security or {}
    row = score or {}
    name = display_company_name(
        sec.get("name_local"),
        row.get("name_local"),
        card.name_local if card is not None else None,
        ticker=ticker,
        market=market,
    )
    return name or ticker


def _reason_codes_for_score(row: dict[str, Any]) -> list[str]:
    existing = row.get("reason_codes")
    if isinstance(existing, list) and existing:
        return [str(c) for c in existing]
    try:
        return assign_reason_codes(pd.Series(row))
    except Exception:
        return []


def _prefer_horizon(rows: list[dict[str, Any]], horizon: str | None) -> dict[str, Any] | None:
    if not rows:
        return None
    if horizon:
        matched = [r for r in rows if r.get("horizon") == horizon]
        if matched:
            return matched[0]
    for preferred in ("H20", "H5"):
        matched = [r for r in rows if r.get("horizon") == preferred]
        if matched:
            return matched[0]
    return rows[0]


def _card_from_rec(
    state: AppState, rec: dict[str, Any], security: dict[str, Any] | None
) -> RecommendationCard | None:
    try:
        if rec.get("thesis_ja") and rec.get("bear_case_ja"):
            return recommendation_from_row(rec, security=security)
    except Exception:
        return None
    return None


def _item_from_parts(
    *,
    state: AppState,
    ticker: str,
    market: str,
    as_of: dt.date,
    score: dict[str, Any] | None,
    rec: dict[str, Any] | None,
    security: dict[str, Any] | None,
) -> RecommendationFeedItem:
    card = _card_from_rec(state, rec, security) if rec else None
    name = _company_name(
        ticker=ticker, market=market, security=security, score=score, card=card
    )
    sec = security or {}
    row = score or {}
    total = _num(row.get("total_score"))
    quant = _num(row.get("quant_score"))
    if card is not None:
        total = total if total is not None else _num(card.total_score)
        quant = quant if quant is not None else _num(card.quant_score)
    reasons = list(card.reason_codes) if card is not None else _reason_codes_for_score(row)
    pred = _num(row.get("ml_pred_h20"))
    if pred is None and card is not None:
        pred = _num(card.ml_pred) if card.ml_pred is not None else _num(card.expected_ret)
    return RecommendationFeedItem(
        ticker=ticker,
        market=market,  # type: ignore[arg-type]
        as_of=as_of,
        name_local=name,
        sector_code=row.get("sector_code") or sec.get("sector_code") or (card.sector_code if card else None),
        sector_name=row.get("sector_name") or sec.get("sector_name") or (card.sector_name if card else None),
        display_tier=_display_tier(card),  # type: ignore[arg-type]
        total_score=total,
        quant_score=quant,
        quant_rank=row.get("quant_rank") if row.get("quant_rank") is not None else (card.quant_rank if card else None),
        quant_percentile=(
            _num(row.get("quant_percentile"))
            if row.get("quant_percentile") is not None
            else (card.quant_percentile if card else None)
        ),
        ml_pred_h20=pred,
        ml_pred_h20_lo=_num(row.get("ml_pred_h20_lo"))
        if row.get("ml_pred_h20_lo") is not None
        else (card.expected_ret_lo if card else None),
        ml_pred_h20_hi=_num(row.get("ml_pred_h20_hi"))
        if row.get("ml_pred_h20_hi") is not None
        else (card.expected_ret_hi if card else None),
        reason_codes=reasons,
        critic_verdict=card.critic_verdict if card is not None else None,
        rec_id=card.rec_id if card is not None else None,
        action=card.action if card is not None else None,
        horizon=card.horizon if card is not None else None,
        conviction=card.conviction if card is not None else None,
        card=card,
    )


def _load_scores(state: AppState, *, market: str, as_of: dt.date | None) -> list[dict[str, Any]]:
    rows = state.duck.get_scores(
        market=market, as_of=as_of, limit=UNIVERSE_FETCH_LIMIT, offset=0
    )
    if rows:
        return list(rows)
    if state.is_seed_data and state.payload:
        seed = state.payload.get("screener") or {}
        out: list[dict[str, Any]] = []
        for row in seed.get("rows") or []:
            item = {
                **row,
                "market": row.get("market") or market,
                "as_of": as_date(row.get("as_of") or seed.get("as_of")) or as_of,
                "quant_score": row.get("quant_score")
                if row.get("quant_score") is not None
                else row.get("total_score"),
            }
            out.append(item)
        return out
    return []


def _load_recs(
    state: AppState,
    *,
    market: str,
    as_of: dt.date | None,
    horizon: str | None,
) -> list[dict[str, Any]]:
    db_rows = state.duck.get_recommendations(
        as_of=as_of,
        market=market,
        include_rejected=True,
        limit=UNIVERSE_FETCH_LIMIT,
        offset=0,
    )
    if db_rows:
        return list(db_rows)
    if state.is_seed_data and state.payload:
        out: list[dict[str, Any]] = []
        for row in state.payload.get("recommendations") or []:
            if market and row.get("market") != market:
                continue
            if as_of and as_date(row.get("as_of")) != as_of:
                continue
            out.append(row)
        return out
    return []


def _index_recs(
    recs: list[dict[str, Any]], *, horizon: str | None
) -> dict[tuple[str, str], dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in recs:
        key = issuer_key(row.get("market"), row.get("ticker"))
        grouped.setdefault(key, []).append(row)
    return {key: chosen for key, rows in grouped.items() if (chosen := _prefer_horizon(rows, horizon))}


def _matches(item: RecommendationFeedItem, query: FeedQuery) -> bool:
    if query.sector:
        needle = query.sector.strip()
        sector = f"{item.sector_name or ''} {item.sector_code or ''}"
        if needle not in sector:
            return False
    if query.min_score is not None:
        score = item.total_score if item.total_score is not None else item.quant_score
        if score is None or score < query.min_score:
            return False
    if query.reason_codes:
        have = set(item.reason_codes)
        if not have.intersection(query.reason_codes):
            return False
    if query.pred_sign == "positive":
        if item.ml_pred_h20 is None or item.ml_pred_h20 <= 0:
            return False
    if query.pred_sign == "negative":
        if item.ml_pred_h20 is None or item.ml_pred_h20 >= 0:
            return False
    if query.has_card is True and item.card is None:
        return False
    if query.has_card is False and item.card is not None:
        return False
    if query.actions and (item.action is None or item.action not in query.actions):
        return False
    if query.convictions and (item.conviction is None or item.conviction not in query.convictions):
        return False
    if query.critic_verdicts:
        if item.critic_verdict is None or item.critic_verdict not in query.critic_verdicts:
            return False
    if not query.include_rejected and item.critic_verdict == "rejected":
        if item.display_tier != "score_only":
            # 却下カードは承認扱いにせず、スコア行として残すため呼び出し側で落とす。
            return item.card is None
    return True


def _sort_key_universe(item: RecommendationFeedItem, sort: str) -> tuple:
    if sort == "quant_score":
        value = item.quant_score
    elif sort == "expected_ret":
        value = item.ml_pred_h20
    else:
        value = item.total_score if item.total_score is not None else item.quant_score
    missing = value is None
    return (missing, -(float(value) if value is not None else 0.0))


def _sort_key_highlight(item: RecommendationFeedItem) -> tuple:
    verdict = item.critic_verdict if item.card is not None else None
    return (
        _TIER_RANK.get(item.display_tier, 9),
        _VERDICT_RANK.get(verdict, 2),
        -_score_value(item),
    )


def _rec_specific_filters(query: FeedQuery) -> bool:
    return bool(
        query.actions
        or query.convictions
        or query.critic_verdicts
        or query.has_card is not None
    )


def build_recommendation_feed(state: AppState, query: FeedQuery) -> RecommendationList:
    market = query.market
    day = query.as_of or state.duck.latest_score_date(market) or state.duck.latest_recommendation_date(
        market
    )
    if day is None and state.is_seed_data:
        day = state.as_of
    scores = _load_scores(state, market=market, as_of=day)
    recs = _load_recs(state, market=market, as_of=day, horizon=query.horizon)
    rec_index = _index_recs(recs, horizon=query.horizon)

    identity_rows = scores if scores else recs
    secs = securities_by_issuer(state.duck, identity_rows) if identity_rows else {}

    items: list[RecommendationFeedItem] = []
    seen: set[tuple[str, str]] = set()

    source_rows = scores if scores else recs
    for row in source_rows:
        ticker = str(row.get("ticker") or "")
        row_market = str(row.get("market") or market)
        key = issuer_key(row_market, ticker)
        if not ticker or key in seen:
            continue
        seen.add(key)
        rec = rec_index.get(key) if scores else row
        if rec and not query.include_rejected and rec.get("critic_verdict") == "rejected":
            rec = None
        score_row = row if scores else None
        as_of = as_date(row.get("as_of")) or as_date(day) or state.as_of
        items.append(
            _item_from_parts(
                state=state,
                ticker=ticker,
                market=row_market,
                as_of=as_of,
                score=score_row,
                rec=rec,
                security=secs.get(key),
            )
        )

    if scores:
        for key, rec in rec_index.items():
            if key in seen:
                continue
            if not query.include_rejected and rec.get("critic_verdict") == "rejected":
                continue
            ticker = str(rec.get("ticker") or "")
            row_market = str(rec.get("market") or market)
            seen.add(key)
            items.append(
                _item_from_parts(
                    state=state,
                    ticker=ticker,
                    market=row_market,
                    as_of=as_date(rec.get("as_of")) or as_date(day) or state.as_of,
                    score=None,
                    rec=rec,
                    security=secs.get(key),
                )
            )

    items = unique_by_issuer([item.model_dump() for item in items])  # type: ignore[arg-type]
    items = [RecommendationFeedItem.model_validate(row) for row in items]
    universe_size = len(items)

    matched = [item for item in items if _matches(item, query)]
    if query.highlights:
        matched.sort(key=_sort_key_highlight)
    else:
        matched.sort(key=lambda item: _sort_key_universe(item, query.sort))

    filled_count = 0
    if query.highlights:
        page = matched[:HIGHLIGHT_COUNT]
        total = len(page)
        return RecommendationList(
            items=page,
            total=total,
            universe_size=universe_size,
            filled_count=sum(1 for i in page if i.display_tier == "score_only"),
            limit=HIGHLIGHT_COUNT,
            offset=0,
        )

    if (
        not _rec_specific_filters(query)
        and query.min_score is None
        and not query.reason_codes
        and not query.sector
        and query.pred_sign is None
        and universe_size < MIN_VISIBLE_RECOMMENDATIONS
    ):
        filled_count = 0

    total = len(matched)
    page = matched[query.offset : query.offset + query.limit]
    return RecommendationList(
        items=page,
        total=total,
        universe_size=universe_size,
        filled_count=filled_count,
        limit=query.limit,
        offset=query.offset,
    )


def feed_item_from_card(card: RecommendationCard) -> RecommendationFeedItem:
    return RecommendationFeedItem(
        ticker=card.ticker,
        market=card.market,
        as_of=card.as_of,
        name_local=card.name_local,
        sector_code=card.sector_code,
        sector_name=card.sector_name,
        display_tier=_display_tier(card),  # type: ignore[arg-type]
        total_score=card.total_score,
        quant_score=card.quant_score,
        quant_rank=card.quant_rank,
        quant_percentile=card.quant_percentile,
        ml_pred_h20=card.ml_pred if card.ml_pred is not None else card.expected_ret,
        ml_pred_h20_lo=card.expected_ret_lo,
        ml_pred_h20_hi=card.expected_ret_hi,
        reason_codes=list(card.reason_codes),
        critic_verdict=card.critic_verdict,
        rec_id=card.rec_id,
        action=card.action,
        horizon=card.horizon,
        conviction=card.conviction,
        card=card,
    )


def seed_cards(state: AppState) -> list[RecommendationCard]:
    return [recommendation_from_seed(row) for row in state.payload.get("recommendations") or []]
