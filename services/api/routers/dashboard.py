"""ダッシュボード（docs/09-api-spec.md §2.1）。"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query

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
from services.api.mapping import recommendation_from_seed
from services.api.util import as_date, as_utc, split_csv

router = APIRouter(tags=["dashboard"])


def _dashboard_from_seed(state: AppState, *, market: str, as_of: dt.date) -> Dashboard:
    payload = state.payload
    dash = payload.get("dashboard") or {}
    fx_raw = payload.get("fx") or {}
    model = payload.get("model_health") or {}
    jobs = payload.get("jobs") or []
    alerts_raw = payload.get("alerts") or []
    recs = payload.get("recommendations") or []
    port = payload.get("portfolio") or {}
    filings = payload.get("filings") or []
    watch = payload.get("watchlist") or []
    watch_tickers = {(w.get("market"), w.get("ticker")) for w in watch}

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
        key = (doc.get("market"), doc.get("ticker"))
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


@router.get("/dashboard", response_model=Envelope[Dashboard])
def get_dashboard(
    market: str = Query(default="JP"),
    as_of: dt.date | None = None,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[Dashboard]:
    day = as_of or state.as_of
    if state.payload:
        data = _dashboard_from_seed(state, market=market, as_of=day)
        return wrap(state, data, as_of=day)
    recs = state.duck.get_recommendations(market=market, as_of=day, limit=5)
    summaries = []
    for row in recs:
        sec = state.duck.get_security(row["ticker"], row["market"]) or {}
        summaries.append(
            RecommendationSummary(
                rec_id=row["rec_id"],
                as_of=as_date(row["as_of"]) or day,
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
    data = Dashboard(as_of=day, market=market, top_recommendations=summaries)  # type: ignore[arg-type]
    return wrap(state, data, as_of=day)
