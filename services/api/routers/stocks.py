"""銘柄詳細（docs/09-api-spec.md §2.4）。"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query, Response

from packages.core.storage import unique_by_issuer
from packages.schemas.common import Envelope
from packages.schemas.documents import DocumentList
from packages.schemas.recommendations import (
    RecommendationHistory,
    RecommendationHistoryRow,
)
from packages.schemas.stocks import (
    FeatureRow,
    FeaturesResponse,
    FinancialPeriod,
    FinancialsResponse,
    KeyMetrics,
    PeerRow,
    PeersResponse,
    PriceBar,
    PriceOverlays,
    PriceSeriesResponse,
    SecuritySearchHit,
    SecuritySearchResult,
    StockDetail,
)
from services.api.deps import AppState, User, get_app_state, require_user
from services.api.envelope import wrap
from services.api.errors import not_found
from services.api.mapping import (
    document_from_row,
    map_doc_type,
    security_from_row,
)
from services.api.util import as_date, as_utc, parse_range_start, resolve_market

router = APIRouter(tags=["stocks"])


def _seed_stock(state: AppState, market: str, ticker: str) -> dict | None:
    key = f"{market}:{ticker}"
    detail = (state.payload.get("stock_detail") or {}).get(key)
    if detail:
        return detail
    for rec in state.payload.get("recommendations") or []:
        if rec.get("market") == market and rec.get("ticker") == ticker:
            return rec
    for item in state.payload.get("watchlist") or []:
        if item.get("market") == market and item.get("ticker") == ticker:
            return item
    return None


@router.get("/stocks/search", response_model=Envelope[SecuritySearchResult])
def search_stocks(
    q: str = Query(min_length=1),
    market: str | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[SecuritySearchResult]:
    if market:
        market = resolve_market(market)
    rows = state.duck.search_securities(q, market=market, limit=limit)
    items = [
        SecuritySearchHit(
            ticker=r["ticker"],
            market=r["market"],
            name_local=r["name_local"],
            name_en=r.get("name_en"),
            sector_name=r.get("sector_name"),
        )
        for r in unique_by_issuer(rows)
    ]
    if not items:
        q_lower = q.lower()
        for rec in state.payload.get("recommendations") or []:
            blob = f"{rec.get('ticker','')} {rec.get('name_local','')} {rec.get('name_en','')}".lower()
            if q_lower in blob or rec.get("ticker", "").startswith(q):
                if market and rec.get("market") != market:
                    continue
                items.append(
                    SecuritySearchHit(
                        ticker=rec["ticker"],
                        market=rec["market"],
                        name_local=rec["name_local"],
                        name_en=rec.get("name_en"),
                        sector_name=rec.get("sector_name"),
                    )
                )
            if len(items) >= limit:
                break
        items = unique_by_issuer(
            [hit.model_dump() for hit in items]
        )
        items = [SecuritySearchHit.model_validate(row) for row in items]
    return wrap(state, SecuritySearchResult(query=q, items=items[:limit], total=len(items)))


@router.get("/stocks/{market}/{ticker}", response_model=Envelope[StockDetail])
def get_stock(
    market: str,
    ticker: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[StockDetail]:
    sec = state.duck.get_security(ticker, market)
    seed = _seed_stock(state, market, ticker)
    if not sec and not seed:
        raise not_found(f"{market}:{ticker} は存在しません。")
    if sec:
        security = security_from_row(sec)
    else:
        security = security_from_row(
            {
                "ticker": ticker,
                "market": market,
                "name_local": seed.get("name_local") or ticker,
                "name_en": seed.get("name_en"),
                "sector_code": seed.get("sector_code"),
                "sector_name": seed.get("sector_name"),
                "currency": "JPY" if market == "JP" else "USD",
                "trading_unit": seed.get("trading_unit"),
                "exchange": seed.get("exchange_ja"),
            }
        )
    km_raw = (seed or {}).get("key_metrics") or {}
    live = state.duck.get_latest_live_quote(ticker, market)
    return wrap(
        state,
        StockDetail(
            security=security,
            ref_price=(seed or {}).get("ref_price") or (live or {}).get("close"),
            ref_change_pct=(seed or {}).get("ref_change_pct") or (live or {}).get("change_pct"),
            ref_change_abs=(seed or {}).get("ref_change_abs"),
            ref_source=(seed or {}).get("ref_source") or (live or {}).get("source"),
            ref_as_of=as_utc((seed or {}).get("ref_as_of")) or as_date((live or {}).get("trade_date")),
            ref_is_delayed=bool((seed or {}).get("ref_is_delayed", True)),
            ref_note_ja="参考値（遅延）" if market == "JP" else None,
            total_score=(seed or {}).get("total_score"),
            quant_score=(seed or {}).get("quant_score"),
            conviction=(seed or {}).get("conviction"),
            key_metrics=KeyMetrics(
                market_cap=km_raw.get("market_cap_jpy") or km_raw.get("market_cap_usd") or km_raw.get("market_cap"),
                currency="JPY" if market == "JP" else "USD",
                per_trailing=km_raw.get("per_trailing"),
                per_forward=km_raw.get("per_forward"),
                pbr=km_raw.get("pbr"),
                ev_ebitda=km_raw.get("ev_ebitda"),
                dividend_yield=km_raw.get("dividend_yield"),
                roe=km_raw.get("roe"),
                roic=km_raw.get("roic"),
                equity_ratio=km_raw.get("equity_ratio"),
                realized_vol_60d=km_raw.get("realized_vol_60d"),
                garch_vol=km_raw.get("garch_vol"),
                adv_20d=km_raw.get("adv_20d_jpy") or km_raw.get("adv_20d_usd"),
                beta_market=km_raw.get("beta_topix") or km_raw.get("beta_spx"),
                fx_sensitivity=km_raw.get("fx_sensitivity"),
                next_earnings_date=as_date(km_raw.get("next_earnings_date")),
                days_to_earnings=km_raw.get("days_to_earnings"),
                financials_filed_at=as_date(km_raw.get("financials_filed_at")),
            )
            if km_raw
            else None,
        ),
    )


@router.get("/stocks/{market}/{ticker}/prices", response_model=Envelope[PriceSeriesResponse])
def get_prices(
    market: str,
    ticker: str,
    response: Response,
    range: str = Query(default="1y"),
    series: str = Query(default="research"),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[PriceSeriesResponse]:
    response.headers["Cache-Control"] = "max-age=300"
    start = parse_range_start(range, as_of=state.as_of)
    seed_prices = ((state.payload.get("prices") or {}).get(f"{market}:{ticker}") or {})
    if series == "live":
        bars_raw = state.duck.get_prices_daily(ticker, market, start=start)  # live is separate table
        live = []
        # prices_live は日次1行なので query する
        live_rows = state.duck.query(
            "SELECT * FROM prices_live WHERE ticker = ? AND market = ? AND trade_date >= ? ORDER BY trade_date",
            [ticker, market, start],
        )
        source_rows = live_rows or (seed_prices.get("live") or {}).get("sample") or []
        bars = [
            PriceBar(
                date=as_date(r.get("date") or r.get("trade_date")) or state.as_of,
                open=r.get("open"),
                high=r.get("high"),
                low=r.get("low"),
                close=r.get("close"),
                volume=r.get("volume"),
                adj_close=r.get("adj_close") or r.get("close"),
            )
            for r in source_rows
        ]
        live_meta = seed_prices.get("live") or {}
        data = PriceSeriesResponse(
            ticker=ticker,
            market=market,  # type: ignore[arg-type]
            series="live",
            source=str(live_meta.get("source") or "yfinance"),
            is_delayed=True,
            delay_note_ja="参考現在値（約15分遅延）。モデル学習には使えません。",
            model_use_forbidden=True,
            latest_as_of=as_utc(live_meta.get("latest_as_of")) or (bars[-1].date if bars else None),
            bars=bars,
        )
        return wrap(state, data)
    rows = state.duck.get_prices_daily(ticker, market, start=start)
    source_rows = rows or (seed_prices.get("research") or {}).get("sample") or []
    bars = [
        PriceBar(
            date=as_date(r.get("date") or r.get("trade_date")) or state.as_of,
            open=r.get("open"),
            high=r.get("high"),
            low=r.get("low"),
            close=r.get("close"),
            volume=r.get("volume"),
            adj_close=r.get("adj_close") or r.get("close"),
        )
        for r in source_rows
    ]
    research_meta = seed_prices.get("research") or {}
    overlays = seed_prices.get("overlays") or {}
    data = PriceSeriesResponse(
        ticker=ticker,
        market=market,  # type: ignore[arg-type]
        series="research",
        source=str(research_meta.get("source") or ("jquants" if market == "JP" else "yfinance")),
        is_delayed=market == "JP",
        delay_note_ja=research_meta.get("delay_note_ja")
        or ("無料プランのため12週遅延" if market == "JP" else None),
        model_use_forbidden=False,
        latest_as_of=as_date(research_meta.get("latest_as_of")) or (bars[-1].date if bars else None),
        bars=bars,
        overlays=PriceOverlays.model_validate(overlays) if overlays else None,
        earnings_markers=seed_prices.get("earnings_markers") or [],
        recommendation_markers=seed_prices.get("recommendation_markers") or [],
    )
    return wrap(state, data)


@router.get("/stocks/{market}/{ticker}/financials", response_model=Envelope[FinancialsResponse])
def get_financials(
    market: str,
    ticker: str,
    periods: int = Query(default=8, ge=1, le=40),
    as_of: dt.date | None = None,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[FinancialsResponse]:
    day = as_of or state.as_of
    rows = state.duck.get_financials_as_of(ticker, market, day, limit=periods)
    seed = ((state.payload.get("financials") or {}).get(f"{market}:{ticker}") or {}).get("periods") or []
    source = rows or seed
    out = []
    for r in source[:periods]:
        out.append(
            FinancialPeriod(
                fiscal_period=str(r.get("fiscal_period") or ""),
                period_end=as_date(r.get("period_end")),
                filed_at=as_date(r.get("filed_at")) or day,
                source_doc_id=r.get("source_doc_id") or r.get("doc_id"),
                revenue=r.get("revenue"),
                operating_income=r.get("operating_income"),
                operating_margin=r.get("operating_margin"),
                net_income=r.get("net_income"),
                eps=r.get("eps"),
                free_cash_flow=r.get("free_cash_flow"),
                operating_cf=r.get("operating_cf"),
                capex=r.get("capex"),
                accruals_ratio=r.get("accruals_ratio"),
                net_debt_ebitda=r.get("net_debt_ebitda"),
                revenue_yoy=r.get("revenue_yoy"),
                operating_income_yoy=r.get("operating_income_yoy"),
                forecast_revenue=r.get("forecast_revenue"),
                forecast_op_income=r.get("forecast_op_income"),
                is_restated=bool(r.get("is_restated") or r.get("restated")),
                restated_note_ja=r.get("restated_note_ja"),
                currency=r.get("currency") or ("JPY" if market == "JP" else "USD"),
            )
        )
    return wrap(
        state,
        FinancialsResponse(ticker=ticker, market=market, basis="filed_at", periods=out),  # type: ignore[arg-type]
        as_of=day,
    )


@router.get("/stocks/{market}/{ticker}/features", response_model=Envelope[FeaturesResponse])
def get_features(
    market: str,
    ticker: str,
    as_of: dt.date | None = None,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[FeaturesResponse]:
    day = as_of or state.as_of
    seed = (state.payload.get("factors") or {}).get(f"{market}:{ticker}")
    if seed:
        rows = [FeatureRow.model_validate(r) for r in seed.get("rows") or []]
        return wrap(
            state,
            FeaturesResponse(
                ticker=ticker,
                market=market,  # type: ignore[arg-type]
                as_of=as_date(seed.get("as_of")) or day,
                feature_version=seed.get("feature_version"),
                n_missing=0,
                rows=rows,
            ),
            as_of=day,
        )
    feat = state.duck.get_features(ticker, market, day)
    rows = []
    if feat:
        for group, key in (
            ("value", "per"),
            ("momentum", "mom_12_1"),
            ("quality", "roic"),
            ("growth", "revenue_growth_yoy"),
            ("lowvol", "realized_vol_60d"),
            ("liquidity", "adv_20d"),
            ("revision", "forecast_revision_magnitude"),
        ):
            rows.append(FeatureRow(group=group, label_ja=group, z_score=feat.get(key)))
    return wrap(
        state,
        FeaturesResponse(
            ticker=ticker,
            market=market,  # type: ignore[arg-type]
            as_of=day,
            feature_version=(feat or {}).get("feature_version"),
            n_missing=(feat or {}).get("n_missing"),
            rows=rows,
        ),
        as_of=day,
    )


@router.get("/stocks/{market}/{ticker}/documents", response_model=Envelope[DocumentList])
def get_stock_documents(
    market: str,
    ticker: str,
    doc_type: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[DocumentList]:
    mapped = map_doc_type(doc_type) if doc_type else None
    rows = state.duck.get_documents(ticker=ticker, market=market, doc_type=mapped, limit=limit)
    items = [document_from_row(r) for r in rows]
    if not items:
        for row in state.payload.get("filings") or []:
            if row.get("ticker") == ticker and row.get("market") == market:
                if mapped and map_doc_type(row.get("doc_type")) != mapped:
                    continue
                items.append(document_from_row(row, has_summary=bool(row.get("has_summary"))))
    return wrap(state, DocumentList(items=items[:limit], total=len(items), limit=limit, offset=0))


@router.get("/stocks/{market}/{ticker}/recommendations", response_model=Envelope[RecommendationHistory])
def get_stock_recommendations(
    market: str,
    ticker: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[RecommendationHistory]:
    hist = (state.payload.get("recommendation_history") or {}).get(f"{market}:{ticker}")
    if hist:
        rows = [RecommendationHistoryRow.model_validate(r) for r in hist.get("rows") or []]
        return wrap(
            state,
            RecommendationHistory(
                ticker=ticker,
                market=market,  # type: ignore[arg-type]
                n=int(hist.get("n") or len(rows)),
                hit_rate=hist.get("hit_rate"),
                avg_excess_return=hist.get("avg_excess_return"),
                rows=rows,
            ),
        )
    recs = state.duck.get_recommendations(market=market, ticker=ticker, include_rejected=True, limit=50)
    rows = []
    for rec in recs:
        rows.append(
            RecommendationHistoryRow(
                rec_id=rec["rec_id"],
                generated_at=as_utc(rec.get("generated_at")) or as_date(rec.get("as_of")) or state.as_of,
                action=rec["action"],
                horizon=rec["horizon"],
                conviction=rec["conviction"],
                expected_ret=rec.get("expected_ret"),
                expected_ret_lo=rec.get("expected_ret_lo"),
                expected_ret_hi=rec.get("expected_ret_hi"),
                outcome="pending",
            )
        )
    return wrap(
        state,
        RecommendationHistory(
            ticker=ticker, market=market, n=len(rows), rows=rows  # type: ignore[arg-type]
        ),
    )


@router.get("/stocks/{market}/{ticker}/peers", response_model=Envelope[PeersResponse])
def get_peers(
    market: str,
    ticker: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[PeersResponse]:
    seed = (state.payload.get("peers") or {}).get(f"{market}:{ticker}") or []
    peers = [
        PeerRow(
            ticker=r["ticker"],
            market=market,  # type: ignore[arg-type]
            name_local=r["name_local"],
            total_score=r.get("total_score"),
            per_forward=r.get("per_forward"),
            pbr=r.get("pbr"),
            roic=r.get("roic"),
            return_20d=r.get("return_20d"),
            fx_sensitivity=r.get("fx_sensitivity"),
        )
        for r in seed
    ]
    if not peers:
        sec = state.duck.get_security(ticker, market)
        sector = (sec or {}).get("sector_code")
        if sector:
            others = [
                r
                for r in state.duck.get_securities(market=market)
                if r.get("sector_code") == sector and r["ticker"] != ticker
            ][:8]
            peers = [
                PeerRow(ticker=r["ticker"], market=market, name_local=r["name_local"])  # type: ignore[arg-type]
                for r in others
            ]
    sec = state.duck.get_security(ticker, market) or _seed_stock(state, market, ticker) or {}
    return wrap(
        state,
        PeersResponse(
            ticker=ticker,
            market=market,  # type: ignore[arg-type]
            sector_name=sec.get("sector_name"),
            peers=peers,
        ),
    )
