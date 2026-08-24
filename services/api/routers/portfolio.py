"""ポートフォリオ・売買日誌（docs/09-api-spec.md §2.9）。"""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, File, Query, UploadFile
from ulid import ULID

from packages.core.storage import to_dict
from packages.schemas.common import Envelope, OkResponse
from packages.schemas.portfolio import (
    ExecutionQuality,
    JournalStats,
    Portfolio,
    PortfolioPerformance,
    PositionList,
    RecommendationQuality,
    TradeAnalysis,
    TradeCreate,
    TradeImportResult,
    TradeList,
    TradePatch,
)
from packages.schemas.portfolio import Position as PositionSchema
from packages.schemas.portfolio import Trade as TradeSchema
from services.api.deps import AppState, User, get_app_state, require_user
from services.api.envelope import wrap
from services.api.errors import not_found, validation_error
from services.api.mapping import position_from_row, trade_from_row
from services.api.util import as_iso, utc_now

router = APIRouter(tags=["portfolio"])


@router.get("/portfolio", response_model=Envelope[Portfolio])
def get_portfolio(
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[Portfolio]:
    raw = state.payload.get("portfolio") or {}
    if raw:
        return wrap(state, Portfolio.model_validate(raw))
    positions = state.sqlite.get_positions()
    return wrap(
        state,
        Portfolio(as_of=state.as_of, n_positions=len(positions), base_currency="JPY"),
    )


@router.get("/portfolio/positions", response_model=Envelope[PositionList])
def get_positions(
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[PositionList]:
    rows = state.sqlite.get_positions()
    seed_by = {(p.get("market"), p.get("ticker")): p for p in state.payload.get("positions") or []}
    items = [
        position_from_row(r, extra=seed_by.get((r.market, r.ticker)))
        for r in rows
    ]
    if not items:
        items = [PositionSchema.model_validate(p) for p in state.payload.get("positions") or []]
    return wrap(state, PositionList(items=items, total=len(items)))


@router.get("/portfolio/performance", response_model=Envelope[PortfolioPerformance])
def get_performance(
    range: str = Query(default="1y"),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[PortfolioPerformance]:
    raw = (state.payload.get("portfolio") or {}).get("performance") or {}
    data = PortfolioPerformance(
        range=raw.get("range") or range,
        portfolio_return=raw.get("portfolio_return"),
        benchmark_return=raw.get("benchmark_return"),
        excess_return=raw.get("excess_return"),
        benchmark_label_ja=raw.get("benchmark_label_ja"),
    )
    return wrap(state, data)


@router.get("/trades", response_model=Envelope[TradeList])
def list_trades(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    ticker: str | None = None,
    market: str | None = None,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[TradeList]:
    rows = state.sqlite.get_trades(ticker=ticker, market=market, limit=limit, offset=offset)
    total = state.sqlite.count_trades(ticker=ticker, market=market)
    items = [trade_from_row(r) for r in rows]
    if not items and offset == 0:
        seed = state.payload.get("trades") or []
        items = [TradeSchema.model_validate({**t, "trade_id": str(t["trade_id"])}) for t in seed]
        total = len(items)
        items = items[offset : offset + limit]
    return wrap(state, TradeList(items=items, total=total, limit=limit, offset=offset))


@router.post("/trades", response_model=Envelope[TradeSchema])
def create_trade(
    body: TradeCreate,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[TradeSchema]:
    trade_id = str(ULID())
    row = state.sqlite.insert_trade(
        trade_id=trade_id,
        ticker=body.ticker,
        market=body.market,
        side=body.side,
        quantity=body.quantity,
        price=body.price,
        fee=body.fee,
        currency=body.currency,
        executed_at=as_iso(body.executed_at) or utc_now().isoformat().replace("+00:00", "Z"),
        broker=body.broker,
        account_type=body.account_type,
        linked_rec_id=body.linked_rec_id,
        thesis_ja=body.thesis_ja,
        emotion_tag=body.emotion_tag,
        exit_plan_ja=body.exit_plan_ja,
        review_ja=body.review_ja,
    )
    return wrap(state, trade_from_row(row))


@router.patch("/trades/{trade_id}", response_model=Envelope[TradeSchema])
def patch_trade(
    trade_id: str,
    body: TradePatch,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[TradeSchema]:
    changes = body.model_dump(exclude_none=True)
    if "executed_at" in changes:
        changes["executed_at"] = as_iso(changes["executed_at"])
    row = state.sqlite.update_trade(trade_id, **changes)
    if row is None:
        raise not_found(f"取引 {trade_id} は存在しません。")
    return wrap(state, trade_from_row(row))


@router.delete("/trades/{trade_id}", response_model=Envelope[OkResponse])
def delete_trade(
    trade_id: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[OkResponse]:
    if not state.sqlite.delete_trade(trade_id):
        raise not_found(f"取引 {trade_id} は存在しません。")
    return wrap(state, OkResponse(ok=True, id=trade_id))


@router.post("/trades/import", response_model=Envelope[TradeImportResult])
async def import_trades(
    file: UploadFile = File(...),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[TradeImportResult]:
    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise validation_error("CSV は UTF-8 で保存してください。")
    reader = csv.DictReader(io.StringIO(text))
    n_rows = 0
    n_imported = 0
    n_skipped = 0
    errors: list[str] = []
    required = {"ticker", "market", "side", "quantity", "price", "currency", "executed_at"}
    for i, row in enumerate(reader, start=2):
        n_rows += 1
        missing = [k for k in required if not (row.get(k) or "").strip()]
        if missing:
            n_skipped += 1
            errors.append(f"{i}行目: 必須列が欠けています ({', '.join(missing)})")
            continue
        try:
            state.sqlite.insert_trade(
                trade_id=str(ULID()),
                ticker=row["ticker"].strip(),
                market=row["market"].strip(),
                side=row["side"].strip(),
                quantity=float(row["quantity"]),
                price=float(row["price"]),
                fee=float(row.get("fee") or 0),
                currency=row["currency"].strip(),
                executed_at=row["executed_at"].strip(),
                broker=(row.get("broker") or None),
                account_type=(row.get("account_type") or None),
                linked_rec_id=(row.get("linked_rec_id") or None),
                thesis_ja=(row.get("thesis_ja") or None),
                emotion_tag=(row.get("emotion_tag") or None),
                exit_plan_ja=(row.get("exit_plan_ja") or None),
            )
            n_imported += 1
        except Exception as exc:
            n_skipped += 1
            errors.append(f"{i}行目: {exc}")
    return wrap(
        state,
        TradeImportResult(n_rows=n_rows, n_imported=n_imported, n_skipped=n_skipped, errors_ja=errors),
    )


@router.get("/trades/analysis", response_model=Envelope[TradeAnalysis])
def get_trade_analysis(
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[TradeAnalysis]:
    raw = state.payload.get("trade_analysis") or {}
    if raw:
        return wrap(state, TradeAnalysis.model_validate(raw))
    trades = state.sqlite.get_trades(limit=1000)
    n = len(trades)
    n_from_rec = sum(1 for t in trades if t.linked_rec_id)
    return wrap(
        state,
        TradeAnalysis(
            recommendation_quality=RecommendationQuality(n_recommendations=0, note_ja="実績がまだありません。"),
            execution_quality=ExecutionQuality(
                n_trades=n,
                n_from_recommendation=n_from_rec,
                n_discretionary=n - n_from_rec,
            ),
            journal_stats=JournalStats(n_entries=n),
        ),
    )
