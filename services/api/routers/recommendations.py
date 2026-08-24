"""推奨（docs/09-api-spec.md §2.2）。"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query

from packages.schemas.common import Envelope, OkResponse
from packages.schemas.recommendations import (
    RecommendationCard,
    RecommendationFeedbackRequest,
    RecommendationList,
    RecommendationOutcome,
)
from services.api.deps import AppState, User, get_app_state, require_user
from services.api.envelope import wrap
from services.api.errors import data_not_ready, not_found
from services.api.mapping import recommendation_from_row, recommendation_from_seed
from services.api.util import as_date, as_utc, split_csv, utc_now

router = APIRouter(tags=["recommendations"])


def _seed_cards(state: AppState) -> list[RecommendationCard]:
    return [recommendation_from_seed(row) for row in state.payload.get("recommendations") or []]


def _db_card(state: AppState, row: dict) -> RecommendationCard:
    sec = state.duck.get_security(row["ticker"], row["market"]) or {}
    return recommendation_from_row(row, security=sec)


@router.get("/recommendations", response_model=Envelope[RecommendationList])
def list_recommendations(
    market: str | None = Query(default=None),
    as_of: dt.date | None = None,
    horizon: str | None = None,
    action: str | None = None,
    conviction: str | None = None,
    include_rejected: bool = False,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[RecommendationList]:
    actions = split_csv(action)
    convictions = split_csv(conviction)
    day = as_of
    items: list[RecommendationCard] = []
    db_rows = state.duck.get_recommendations(
        as_of=day,
        market=market,
        horizon=horizon,
        include_rejected=include_rejected,
        limit=500,
        offset=0,
    )
    if db_rows:
        for row in db_rows:
            if actions and row.get("action") not in actions:
                continue
            if convictions and row.get("conviction") not in convictions:
                continue
            items.append(_db_card(state, row))
    elif state.payload:
        for card in _seed_cards(state):
            if market and card.market != market:
                continue
            if day and card.as_of != day:
                continue
            if horizon and card.horizon != horizon:
                continue
            if actions and card.action not in actions:
                continue
            if convictions and card.conviction not in convictions:
                continue
            if not include_rejected and card.critic_verdict == "rejected":
                continue
            items.append(card)
    if day is not None and not items:
        latest = state.duck.latest_recommendation_date(market)
        raise data_not_ready(
            f"{day.isoformat()} の推奨はまだ計算されていません。",
            latest_available_as_of=as_date(latest),
            instance="/api/v1/recommendations",
        )
    total = len(items)
    page = items[offset : offset + limit]
    as_of_out = day or (page[0].as_of if page else state.as_of)
    return wrap(
        state,
        RecommendationList(items=page, total=total, limit=limit, offset=offset),
        as_of=as_of_out,
    )


@router.get("/recommendations/{rec_id}", response_model=Envelope[RecommendationCard])
def get_recommendation(
    rec_id: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[RecommendationCard]:
    row = state.duck.get_recommendation(rec_id)
    if row:
        card = _db_card(state, row)
        return wrap(state, card, as_of=card.as_of)
    for card in _seed_cards(state):
        if card.rec_id == rec_id:
            return wrap(state, card, as_of=card.as_of)
    raise not_found(f"推奨 {rec_id} は存在しません。")


@router.get(
    "/recommendations/{rec_id}/outcome",
    response_model=Envelope[RecommendationOutcome | None],
)
def get_recommendation_outcome(
    rec_id: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[RecommendationOutcome | None]:
    rows = state.duck.get_recommendation_outcomes(rec_id=rec_id, limit=10)
    if not rows:
        # シードの履歴から pending 以外を探す
        history = (state.payload.get("recommendation_history") or {}).get("JP:7203") or {}
        for row in history.get("rows") or []:
            if row.get("rec_id") == rec_id and row.get("outcome") in {"hit", "miss"}:
                outcome = RecommendationOutcome(
                    rec_id=rec_id,
                    horizon=row.get("horizon") or "H20",
                    evaluated_at=as_utc(row.get("generated_at")) or utc_now(),
                    entry_date=as_date(row.get("generated_at")) or state.as_of,
                    exit_date=as_date(row.get("generated_at")) or state.as_of,
                    entry_price=0.0,
                    exit_price=0.0,
                    raw_return=float(row.get("realized_ret") or 0.0),
                    benchmark_return=0.0,
                    excess_return=float(row.get("realized_ret") or 0.0),
                    is_hit=row.get("outcome") == "hit",
                )
                return wrap(state, outcome)
        return wrap(state, None)
    row = rows[0]
    outcome = RecommendationOutcome(
        rec_id=row["rec_id"],
        horizon=row["horizon"],
        evaluated_at=as_utc(row.get("evaluated_at")) or utc_now(),
        entry_date=as_date(row["entry_date"]) or state.as_of,
        exit_date=as_date(row["exit_date"]) or state.as_of,
        entry_price=float(row["entry_price"]),
        exit_price=float(row["exit_price"]),
        raw_return=float(row["raw_return"]),
        benchmark_return=float(row["benchmark_return"]),
        excess_return=float(row["excess_return"]),
        sector_excess_return=row.get("sector_excess_return"),
        is_hit=bool(row["is_hit"]),
        max_favorable_excursion=row.get("max_favorable_excursion"),
        max_adverse_excursion=row.get("max_adverse_excursion"),
        realized_vol=row.get("realized_vol"),
        notes_ja=row.get("notes_ja"),
    )
    return wrap(state, outcome)


@router.post("/recommendations/{rec_id}/feedback", response_model=Envelope[OkResponse])
def post_feedback(
    rec_id: str,
    body: RecommendationFeedbackRequest,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[OkResponse]:
    exists = state.duck.get_recommendation(rec_id) or any(
        r.get("rec_id") == rec_id for r in state.payload.get("recommendations") or []
    )
    if not exists:
        raise not_found(f"推奨 {rec_id} は存在しません。")
    key = "recommendations.feedback"
    current = state.sqlite.get_setting(key, [])
    if not isinstance(current, list):
        current = []
    current.append(
        {
            "rec_id": rec_id,
            "verdict": body.verdict,
            "note_ja": body.note_ja,
            "at": utc_now().isoformat().replace("+00:00", "Z"),
        }
    )
    state.sqlite.set_setting(key, current)
    return wrap(state, OkResponse(ok=True, id=rec_id, message_ja="フィードバックを記録しました。"))
