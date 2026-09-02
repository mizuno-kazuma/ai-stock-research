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
from services.api.recommendation_feed import FeedQuery, build_recommendation_feed
from services.api.util import as_date, as_utc, resolve_market, split_csv, utc_now

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
    horizon: str | None = Query(default="H20"),
    action: str | None = None,
    conviction: str | None = None,
    critic_verdict: str | None = None,
    sector: str | None = None,
    min_score: float | None = None,
    reason_code: str | None = None,
    pred_sign: str | None = Query(default=None, pattern="^(positive|negative)$"),
    has_card: bool | None = None,
    include_rejected: bool = True,
    sort: str = Query(default="total_score"),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[RecommendationList]:
    resolved = resolve_market(market) if market else resolve_market(None)
    pred: str | None = pred_sign if pred_sign in {"positive", "negative"} else None
    feed = build_recommendation_feed(
        state,
        FeedQuery(
            market=resolved,
            as_of=as_of,
            horizon=horizon,
            actions=split_csv(action) or [],
            convictions=split_csv(conviction) or [],
            critic_verdicts=split_csv(critic_verdict) or [],
            sector=sector,
            min_score=min_score,
            reason_codes=split_csv(reason_code) or [],
            pred_sign=pred,  # type: ignore[arg-type]
            has_card=has_card,
            include_rejected=include_rejected,
            limit=limit,
            offset=offset,
            sort=sort,
        ),
    )
    if as_of is not None and feed.universe_size == 0:
        latest = state.duck.latest_score_date(resolved) or state.duck.latest_recommendation_date(
            resolved
        )
        raise data_not_ready(
            f"{as_of.isoformat()} の推奨はまだ計算されていません。",
            latest_available_as_of=as_date(latest),
            instance="/api/v1/recommendations",
        )
    as_of_out = as_of or (feed.items[0].as_of if feed.items else state.as_of)
    return wrap(state, feed, as_of=as_of_out)


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
    if state.is_seed_data:
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
