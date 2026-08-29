"""スコアとスクリーナー（docs/09-api-spec.md §2.3）。"""

from __future__ import annotations

import datetime as dt
import operator
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Query

from packages.schemas.common import Envelope, OkResponse
from packages.schemas.screener import (
    SCREENER_MAX_ROWS,
    SavedScreen,
    SavedScreenCreate,
    ScoreList,
    ScoreRow,
    ScreenerFilter,
    ScreenerPreset,
    ScreenerRequest,
    ScreenerResult,
)
from services.api.deps import AppState, User, get_app_state, require_user
from services.api.envelope import wrap
from services.api.errors import data_not_ready, not_found, validation_error
from services.api.mapping import score_from_row
from services.api.util import as_date, resolve_market, utc_now

router = APIRouter(tags=["screener"])

_OPS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
}

PRESETS = [
    ScreenerPreset(
        preset_id="value_quality",
        name_ja="割安かつ高クオリティ",
        description_ja="PER が低く ROIC が高い銘柄",
        market="JP",
        filters=[
            ScreenerFilter(field="quant_score", op="gte", value=70),
            ScreenerFilter(field="roic", op="gte", value=0.10),
        ],
    ),
    ScreenerPreset(
        preset_id="revision_up",
        name_ja="上方修正",
        description_ja="会社予想が上方に改定された銘柄",
        market="JP",
        filters=[ScreenerFilter(field="forecast_revision_direction", op="eq", value=1)],
    ),
]


def _match_filter(row: dict[str, Any], filt: ScreenerFilter) -> bool:
    value = row.get(filt.field)
    op = filt.op
    if op == "is_null":
        return value is None
    if op == "is_not_null":
        return value is not None
    if value is None:
        return False
    if op == "in":
        return value in (filt.value or [])
    if op == "not_in":
        return value not in (filt.value or [])
    if op == "between":
        lo, hi = filt.value[0], filt.value[1]
        return lo <= value <= hi
    fn = _OPS.get(op)
    if fn is None:
        return True
    return bool(fn(value, filt.value))


def _saved_screens(state: AppState) -> list[dict[str, Any]]:
    raw = state.sqlite.get_setting("screener.saved", [])
    return list(raw) if isinstance(raw, list) else []


@router.get("/scores", response_model=Envelope[ScoreList])
def get_scores(
    market: str = Query(default="JP"),
    as_of: dt.date | None = None,
    ticker: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[ScoreList]:
    market = resolve_market(market)
    day = as_of
    tickers = [ticker] if ticker else None
    rows = state.duck.get_scores(market=market, as_of=day, tickers=tickers, limit=limit, offset=offset)
    if not rows and day is not None:
        latest = state.duck.latest_score_date(market)
        if latest != day:
            raise data_not_ready(
                f"{day.isoformat()} のスコアはまだ計算されていません。",
                latest_available_as_of=as_date(latest),
                instance="/api/v1/scores",
            )
    items: list[ScoreRow] = []
    if rows:
        for row in rows:
            sec = state.duck.get_security(row["ticker"], row["market"]) or {}
            items.append(score_from_row(row, name_local=sec.get("name_local")))
    elif state.payload:
        seed_rows = (state.payload.get("screener") or {}).get("rows") or []
        for row in seed_rows:
            if ticker and row.get("ticker") != ticker:
                continue
            items.append(
                ScoreRow(
                    ticker=row["ticker"],
                    market=market,  # type: ignore[arg-type]
                    as_of=as_date((state.payload.get("screener") or {}).get("as_of")) or state.as_of,
                    name_local=row.get("name_local"),
                    sector_name=row.get("sector_name"),
                    quant_score=row.get("total_score"),
                    total_score=row.get("total_score"),
                )
            )
        items = items[offset : offset + limit]
    return wrap(
        state,
        ScoreList(items=items, total=len(items), limit=limit, offset=offset),
        as_of=day or state.as_of,
    )


@router.post("/screener", response_model=Envelope[ScreenerResult])
def run_screener(
    body: ScreenerRequest,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[ScreenerResult]:
    day = body.as_of or state.as_of
    universe: list[dict[str, Any]] = []
    db_rows = state.duck.get_scores(market=body.market, as_of=body.as_of, limit=SCREENER_MAX_ROWS, offset=0)
    if db_rows:
        for row in db_rows:
            sec = state.duck.get_security(row["ticker"], row["market"]) or {}
            merged = {**row, "name_local": sec.get("name_local"), "sector_name": sec.get("sector_name")}
            universe.append(merged)
    else:
        seed = state.payload.get("screener") or {}
        for row in seed.get("rows") or []:
            universe.append({**row, "market": body.market, "as_of": seed.get("as_of")})

    matched = [row for row in universe if all(_match_filter(row, f) for f in body.filters)]
    if body.sort:
        for spec in reversed(body.sort):
            matched.sort(
                key=lambda r, field=spec.field: (r.get(field) is None, r.get(field)),
                reverse=spec.dir == "desc",
            )
    total = len(matched)
    truncated = total > SCREENER_MAX_ROWS
    matched = matched[:SCREENER_MAX_ROWS]
    page = matched[body.offset : body.offset + body.limit]
    columns = body.columns or (
        list(page[0].keys()) if page else ["ticker", "name_local", "total_score"]
    )
    rows_out = [{k: r.get(k) for k in columns if k in r or True} for r in page]
    # 列指定があればそれに絞る
    if body.columns:
        rows_out = [{k: r.get(k) for k in body.columns} for r in page]
    meta = (state.payload.get("screener") or {}).get("meta") or {}
    result = ScreenerResult(
        as_of=as_date((state.payload.get("screener") or {}).get("as_of")) or day,
        market=body.market,
        columns=columns,
        rows=rows_out,
        total=total,
        limit=body.limit,
        offset=body.offset,
        truncated=truncated or bool(meta.get("truncated")),
        universe_size=meta.get("universe_size") or len(universe),
        excluded_count=meta.get("excluded_count"),
        excluded_reason_ja=meta.get("excluded_reason_ja"),
    )
    return wrap(state, result, as_of=result.as_of)


@router.get("/screener/presets", response_model=Envelope[list[ScreenerPreset]])
def list_presets(
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[list[ScreenerPreset]]:
    return wrap(state, PRESETS)


@router.get("/screener/saved", response_model=Envelope[list[SavedScreen]])
def list_saved(
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[list[SavedScreen]]:
    items = [SavedScreen.model_validate(row) for row in _saved_screens(state)]
    return wrap(state, items)


@router.post("/screener/saved", response_model=Envelope[SavedScreen])
def create_saved(
    body: SavedScreenCreate,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[SavedScreen]:
    screen = SavedScreen(
        id=str(uuid4()),
        name_ja=body.name_ja,
        request=body.request,
        created_at=utc_now(),
    )
    saved = _saved_screens(state)
    saved.append(screen.model_dump(mode="json"))
    state.sqlite.set_setting("screener.saved", saved)
    return wrap(state, screen)


@router.delete("/screener/saved/{saved_id}", response_model=Envelope[OkResponse])
def delete_saved(
    saved_id: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[OkResponse]:
    saved = _saved_screens(state)
    kept = [row for row in saved if str(row.get("id")) != saved_id]
    if len(kept) == len(saved):
        raise not_found(f"保存済みフィルタ {saved_id} は存在しません。")
    state.sqlite.set_setting("screener.saved", kept)
    return wrap(state, OkResponse(ok=True, id=saved_id))
