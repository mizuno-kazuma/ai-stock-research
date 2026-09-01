"""ダッシュボード（docs/09-api-spec.md §2.1）。"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query

from packages.core.models.regime import (
    correlation_regime,
    model_degradation,
    vol_regime_from_levels,
)
from packages.core.storage import issuer_key, unique_by_issuer
from packages.schemas.common import Envelope
from packages.schemas.dashboard import (
    AdvanceDecline,
    Alert,
    BenchmarkQuote,
    CorrelationRegime,
    Dashboard,
    DashboardFx,
    FxForecastBrief,
    JobStatusBrief,
    MarketSummary,
    ModelHealthBrief,
    PortfolioSnapshot,
    TopMover,
    VolRegime,
    WatchlistFiling,
)
from packages.schemas.recommendations import RecommendationSummary
from services.api.deps import AppState, User, get_app_state, require_user
from services.api.envelope import wrap
from services.api.mapping import (
    alert_from_row,
    display_company_name,
    recommendation_from_seed,
    securities_by_issuer,
)
from services.api.util import as_date, as_utc, resolve_market

router = APIRouter(tags=["dashboard"])


def _filings_range(as_of: dt.date) -> tuple[dt.date, dt.date]:
    """「今週の開示」は as_of を含む暦週の月曜から as_of まで（両端含む）。"""
    start = as_of - dt.timedelta(days=as_of.weekday())
    return start, as_of


def _filed_date(value: object) -> dt.date | None:
    parsed = as_utc(value)
    if parsed is not None:
        return parsed.date()
    return as_date(value)


def _macro_levels(state: AppState, series_id: str, as_of: dt.date, limit: int = 1300):
    import pandas as pd

    rows = state.duck.get_macro_as_of(series_id, as_of=as_of, limit=limit)
    if not rows:
        return None
    frame = pd.DataFrame(rows)
    date_col = "observation_date" if "observation_date" in frame.columns else "date"
    if date_col not in frame.columns or "value" not in frame.columns:
        return None
    series = pd.Series(
        pd.to_numeric(frame["value"], errors="coerce").to_numpy(),
        index=pd.to_datetime(frame[date_col], errors="coerce"),
    )
    return series.dropna().sort_index()


def _price_panel(state: AppState, market: str, as_of: dt.date):
    start = as_of - dt.timedelta(days=120)
    try:
        frame = state.duck.read_prices_daily(market=market, start=start, end=as_of)
    except Exception:
        return None
    if frame is None or getattr(frame, "empty", True):
        return None
    if len(frame) > 80_000:
        tickers = list(frame["ticker"].dropna().unique()[:40])
        frame = frame[frame["ticker"].isin(tickers)]
    return frame


def _daily_ics(state: AppState, market: str):
    import pandas as pd

    getter = getattr(state.duck, "get_model_runs", None)
    if not callable(getter):
        return None
    try:
        runs = getter(limit=1) or []
    except Exception:
        return None
    if not runs:
        return None
    row = runs[0] if isinstance(runs[0], dict) else None
    if row is None:
        ics = getattr(runs[0], "fold_rank_ic", None)
    else:
        ics = row.get("fold_rank_ic")
    if not ics:
        return None
    return pd.Series(pd.to_numeric(pd.Series(ics), errors="coerce").dropna())


def _live_regimes(
    state: AppState, *, market: str, as_of: dt.date
) -> tuple[VolRegime | None, CorrelationRegime | None, ModelHealthBrief | None]:
    series_id = "NIKKEI225" if market == "JP" else "SP500"
    levels = _macro_levels(state, series_id, as_of)
    vol = vol_regime_from_levels(levels) if levels is not None else None
    corr = correlation_regime(_price_panel(state, market, as_of))
    ics = _daily_ics(state, market)
    model = model_degradation(ics) if ics is not None else None

    vol_out = None
    if vol is not None and vol.level != "unknown":
        vol_out = VolRegime(
            level=vol.level,
            percentile=vol.percentile,
            message_ja=vol.message_ja,
        )
    corr_out = CorrelationRegime(
        avg_pairwise_corr_60d=corr.avg_pairwise_corr_60d,
        level=corr.level,
    )
    health = None
    if model is not None:
        health = ModelHealthBrief(
            rank_ic_20d=model.rank_ic_20d,
            rank_ic_percentile_1y=model.rank_ic_percentile_1y,
            status="degraded" if model.degraded else "ok",
            coverage_note_ja=model.message_ja,
        )
    return vol_out, corr_out, health


def _dashboard_from_seed(state: AppState, *, market: str, as_of: dt.date) -> Dashboard:
    payload = state.payload
    dash = payload.get("dashboard") or {}
    fx_raw = payload.get("fx") or {}
    model = payload.get("model_health") or {}
    jobs = payload.get("jobs") or []
    alerts_raw = payload.get("alerts") or []
    recs = unique_by_issuer(payload.get("recommendations") or [])
    port = payload.get("portfolio") or {}
    filings = payload.get("filings") or []
    watch = payload.get("watchlist") or []
    watch_tickers = {issuer_key(w.get("market"), w.get("ticker")) for w in watch}
    start, end = _filings_range(as_of)
    filings = [
        doc
        for doc in filings
        if (filed := _filed_date(doc.get("filed_at"))) is not None and start <= filed <= end
    ]

    summaries: list[RecommendationSummary] = []
    for row in recs:
        if row.get("critic_verdict") == "rejected":
            continue
        if row.get("market") != market:
            continue
        card = recommendation_from_seed(row)
        summaries.append(
            RecommendationSummary(
                rec_id=card.rec_id,
                as_of=card.as_of,
                ticker=card.ticker,
                market=card.market,
                name_local=card.name_local,
                sector_name=card.sector_name,
                action=card.action,
                horizon=card.horizon,
                conviction=card.conviction,
                conviction_score=card.conviction_score,
                total_score=card.total_score,
                expected_ret=card.expected_ret,
                expected_ret_lo=card.expected_ret_lo,
                expected_ret_hi=card.expected_ret_hi,
                hit_rate_prior=card.hit_rate_prior,
                n_prior_samples=card.n_prior_samples,
                reason_codes=card.reason_codes,
                flags=card.flags,
            )
        )
        if len(summaries) >= 5:
            break

    index = dash.get("index") or {}
    fx_summary = dash.get("fx_summary") or {}
    h20 = next((f for f in fx_raw.get("forecasts") or [] if f.get("horizon") == "H20"), None)
    last_job = jobs[0] if jobs else {}
    watch_filings = []
    for doc in filings:
        key = issuer_key(doc.get("market"), doc.get("ticker"))
        if key in watch_tickers:
            watch_filings.append(
                WatchlistFiling(
                    doc_id=doc["doc_id"],
                    ticker=doc.get("ticker"),
                    market=doc.get("market"),
                    name_local=doc.get("name_local"),
                    doc_type=doc.get("doc_type") if doc.get("doc_type") not in {"10-Q", "8-K", "other"} else (
                        "quarterly_report" if doc.get("doc_type") == "10-Q"
                        else "current_report" if doc.get("doc_type") == "8-K"
                        else "other_disclosure"
                    ),
                    title=doc.get("title") or doc["doc_id"],
                    filed_at=as_utc(doc.get("filed_at")) or dt.datetime.now(dt.UTC),
                    has_summary=bool(doc.get("has_summary")),
                )
            )

    alerts = []
    for item in alerts_raw:
        if item.get("is_read"):
            continue
        sev = item.get("severity") or "info"
        if sev == "danger":
            sev = "error"
        alerts.append(
            Alert(
                alert_id=str(item.get("alert_id")),
                severity=sev,
                category=item.get("category") or "data",
                title_ja=item.get("title_ja") or "",
                created_at=as_utc(item.get("created_at")) or dt.datetime.now(dt.UTC),
                is_read=False,
                link=item.get("link"),
            )
        )

    pos_movers = [
        TopMover(ticker="6758", change_pct=-0.0421),
        TopMover(ticker="7203", change_pct=0.0124),
    ]
    return Dashboard(
        as_of=as_of,
        market=market,  # type: ignore[arg-type]
        market_summary=MarketSummary(
            benchmark=BenchmarkQuote(
                symbol=index.get("symbol") or "TOPIX",
                label_ja=index.get("label_ja"),
                close=index.get("value"),
                change_pct=index.get("change_pct"),
                change_abs=index.get("change_abs"),
                as_of=as_date(index.get("as_of")),
            ),
            advance_decline=AdvanceDecline(advancing=1420, declining=2180, unchanged=210),
            vol_regime=VolRegime(
                level="elevated",
                percentile=0.78,
                message_ja="ボラティリティは過去5年の78パーセンタイル。推奨の確信度を1段下げています",
            ),
            correlation_regime=CorrelationRegime(avg_pairwise_corr_60d=0.41, level="normal"),
        ),
        fx=DashboardFx(
            pair=fx_summary.get("pair") or fx_raw.get("pair") or "USDJPY",
            spot=fx_summary.get("value") or (fx_raw.get("reference") or {}).get("value"),
            change_pct=fx_summary.get("change_pct"),
            as_of=as_utc(fx_summary.get("as_of")),
            forecast_h20=FxForecastBrief(
                point=(h20 or {}).get("median"),
                ci_lo_80=(h20 or {}).get("lo80"),
                ci_hi_80=(h20 or {}).get("hi80"),
                beats_baseline=(h20 or {}).get("beats_baseline"),
                note_ja=fx_raw.get("verdict_ja"),
            )
            if h20 or fx_raw.get("verdict_ja")
            else None,
        ),
        top_recommendations=summaries,
        portfolio_snapshot=PortfolioSnapshot(
            n_positions=int(port.get("n_positions") or 0),
            unrealized_pnl_pct=port.get("unrealized_pl_pct"),
            day_change_pct=port.get("daily_pl_pct"),
            market_value=port.get("market_value_jpy"),
            currency="JPY",
            top_movers=pos_movers,
        ),
        new_filings_count=len(filings),
        watchlist_filings=watch_filings[:8],
        model_health=ModelHealthBrief(
            rank_ic_20d=model.get("rank_ic_20d"),
            rank_ic_percentile_1y=0.62,
            status="normal" if not model.get("degradation_detected") else "degraded",
            coverage_rate=model.get("coverage_pct"),
            coverage_note_ja=(
                f"カバー率 {model.get('coverage_pct')}。" if model.get("coverage_pct") is not None else None
            ),
        ),
        alerts=alerts,
        job_status=JobStatusBrief(
            last_run=as_utc(last_job.get("finished_at") or last_job.get("started_at")),
            status=last_job.get("status"),
            failed_steps=list(last_job.get("failed_steps") or []),
        )
        if last_job
        else None,
    )


def _unique_recs_by_ticker(rows: list[dict]) -> list[dict]:
    """発行体あたり 1 件。H5 と H20、4桁と 5桁、日付違いを畳む。"""
    return unique_by_issuer(rows)


def _dashboard_from_warehouse(state: AppState, *, market: str, as_of: dt.date) -> Dashboard:
    recs = state.duck.get_recommendations(market=market, as_of=as_of, limit=20)
    if not recs:
        latest = state.duck.latest_recommendation_date(market)
        recs = (
            state.duck.get_recommendations(market=market, as_of=latest, limit=20)
            if latest
            else []
        )
    recs = _unique_recs_by_ticker(recs)[:5]
    summaries: list[RecommendationSummary] = []
    for row in recs:
        sec = state.duck.get_security(row["ticker"], row["market"]) or {}
        summaries.append(
            RecommendationSummary(
                rec_id=row["rec_id"],
                as_of=as_date(row["as_of"]) or as_of,
                ticker=row["ticker"],
                market=row["market"],
                name_local=sec.get("name_local") or row["ticker"],
                sector_name=sec.get("sector_name"),
                action=row["action"],
                horizon=row["horizon"],
                conviction=row["conviction"],
                conviction_score=row["conviction_score"],
                total_score=row.get("total_score"),
                expected_ret=row.get("expected_ret"),
                expected_ret_lo=row.get("expected_ret_lo"),
                expected_ret_hi=row.get("expected_ret_hi"),
                hit_rate_prior=row.get("hit_rate_prior"),
                n_prior_samples=row.get("n_prior_samples"),
                reason_codes=list(row.get("reason_codes") or []),
                flags=list(row.get("flags") or []),
            )
        )

    series_id = "NIKKEI225" if market == "JP" else "SP500"
    bench_rows = state.duck.get_macro_as_of(series_id, as_of=as_of, limit=2)
    vol_regime, corr_regime, model_health = _live_regimes(
        state, market=market, as_of=as_of
    )
    market_summary = None
    if bench_rows or vol_regime or corr_regime.avg_pairwise_corr_60d is not None:
        latest = bench_rows[0] if bench_rows else {}
        prev = bench_rows[1] if len(bench_rows) > 1 else None
        close = latest.get("value")
        change = None
        if close is not None and prev and prev.get("value"):
            change = float(close) / float(prev["value"]) - 1.0
        market_summary = MarketSummary(
            benchmark=BenchmarkQuote(
                symbol=series_id,
                label_ja="日経平均" if market == "JP" else "S&P500",
                close=float(close) if close is not None else None,
                change_pct=change,
                as_of=as_date(latest.get("observation_date")),
            )
            if bench_rows
            else None,
            vol_regime=vol_regime,
            correlation_regime=corr_regime,
        )

    fx = None
    fx_rows = state.duck.get_macro_as_of("DEXJPUS", as_of=as_of, limit=2)
    if fx_rows:
        latest = fx_rows[0]
        prev = fx_rows[1] if len(fx_rows) > 1 else None
        spot = latest.get("value")
        change = None
        if spot is not None and prev and prev.get("value"):
            change = float(spot) / float(prev["value"]) - 1.0
        fx = DashboardFx(
            pair="USDJPY",
            spot=float(spot) if spot is not None else None,
            change_pct=change,
            as_of=as_date(latest.get("observation_date")),
        )

    start, end = _filings_range(as_of)
    watch = {issuer_key(w.market, w.ticker) for w in state.sqlite.get_watchlist()}
    docs = state.duck.get_documents(market=market, since=start, until=end, limit=80)
    preferred = [
        row
        for row in docs
        if not watch or issuer_key(row.get("market"), row.get("ticker")) in watch
    ]
    source_docs = preferred or docs
    secs = securities_by_issuer(state.duck, source_docs)
    watch_filings: list[WatchlistFiling] = []
    for row in source_docs:
        filed = as_utc(row.get("filed_at"))
        if filed is None:
            continue
        sec = secs.get(issuer_key(row.get("market"), row.get("ticker"))) or {}
        watch_filings.append(
            WatchlistFiling(
                doc_id=str(row["doc_id"]),
                ticker=row.get("ticker"),
                market=row.get("market"),
                name_local=display_company_name(
                    sec.get("name_local"),
                    row.get("name_local"),
                    ticker=str(row.get("ticker") or ""),
                    market=str(row.get("market") or market),
                ),
                doc_type=str(row.get("doc_type") or "other_disclosure"),
                title=str(row.get("title") or row["doc_id"]),
                filed_at=filed,
                has_summary=state.duck.get_document_summary(str(row["doc_id"])) is not None,
            )
        )
        if len(watch_filings) >= 8:
            break

    alerts: list[Alert] = []
    for row in state.sqlite.get_alerts(unread_only=True, limit=10):
        item = alert_from_row(row)
        alerts.append(
            Alert(
                alert_id=item.alert_id,
                severity=item.severity,
                category=item.category,
                title_ja=item.title_ja,
                body_ja=item.body_ja,
                created_at=item.created_at,
                is_read=item.is_read,
                link=item.link,
            )
        )

    jobs = state.sqlite.get_job_runs(limit=1)
    job_status = None
    if jobs:
        last = jobs[0]
        job_status = JobStatusBrief(
            last_run=as_utc(getattr(last, "finished_at", None) or getattr(last, "started_at", None)),
            status=getattr(last, "status", None),
            failed_steps=[],
        )

    positions = state.sqlite.get_positions()
    portfolio = PortfolioSnapshot(n_positions=len(positions), currency="JPY")

    return Dashboard(
        as_of=as_of,
        market=market,  # type: ignore[arg-type]
        market_summary=market_summary,
        fx=fx,
        top_recommendations=summaries,
        portfolio_snapshot=portfolio,
        new_filings_count=state.duck.count_documents(market=market, since=start, until=end)
        or len(watch_filings),
        watchlist_filings=watch_filings,
        model_health=model_health,
        alerts=alerts,
        job_status=job_status,
    )


@router.get("/dashboard", response_model=Envelope[Dashboard])
def get_dashboard(
    market: str = Query(default="JP"),
    as_of: dt.date | None = None,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[Dashboard]:
    market = resolve_market(market)
    day = as_of or state.as_of
    if state.is_seed_data and state.payload:
        data = _dashboard_from_seed(state, market=market, as_of=day)
        return wrap(state, data, as_of=day)
    data = _dashboard_from_warehouse(state, market=market, as_of=day)
    return wrap(state, data, as_of=day)
