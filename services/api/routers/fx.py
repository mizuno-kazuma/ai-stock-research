"""為替・マクロ（docs/09-api-spec.md §2.6）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from packages.schemas.common import Envelope
from packages.schemas.fx_macro import (
    Cointegration,
    DieboldMariano,
    FxDetail,
    FxForecast,
    FxHistory,
    FxHistoryPoint,
    FxQuote,
    FxVolForecast,
    MacroPoint,
    MacroSeries,
    MacroSeriesResponse,
    ModelComparisonRow,
    RateDifferential,
    RateDifferentialPoint,
    RateDifferentialResponse,
)
from services.api.deps import AppState, User, get_app_state, require_user
from services.api.envelope import wrap
from services.api.errors import not_found
from services.api.util import as_date, as_utc, parse_range_start

router = APIRouter(tags=["fx-macro"])


def _verdict_ja(*, beats_baseline: bool | None, dm_pvalue: float | None) -> str:
    if beats_baseline:
        p = f"（DM検定 p={dm_pvalue:.2f}）" if dm_pvalue is not None else ""
        return f"ランダムウォークに対する優位性が確認されています{p}。"
    p = f"（DM検定 p={dm_pvalue:.2f}）" if dm_pvalue is not None else ""
    return f"ランダムウォークに対する優位性は確認できていません{p}。参考程度に扱ってください。"


def _fx_from_seed(state: AppState, pair: str) -> FxDetail | None:
    raw = state.payload.get("fx") or {}
    if raw.get("pair") and raw.get("pair") != pair:
        return None
    if not raw:
        return None
    dm = raw.get("diebold_mariano") or {}
    forecasts = []
    horizon_days = {"H5": 5, "H20": 20, "H60": 60}
    for item in raw.get("forecasts") or []:
        pvalue = item.get("p_value")
        beats = bool(item.get("beats_baseline"))
        forecasts.append(
            FxForecast(
                horizon_days=horizon_days.get(item.get("horizon") or "", 20),
                horizon=item.get("horizon"),
                label_ja=item.get("label_ja"),
                model_id=str(item.get("model") or "arimax"),
                point=float(item.get("median") or item.get("point") or 0.0),
                ci_lo_80=float(item.get("lo80") or item.get("ci_lo_80") or 0.0),
                ci_hi_80=float(item.get("hi80") or item.get("ci_hi_80") or 0.0),
                ci_lo_95=item.get("lo95") or item.get("ci_lo_95"),
                ci_hi_95=item.get("hi95") or item.get("ci_hi_95"),
                change_pct=item.get("change_pct"),
                is_baseline=False,
                dm_pvalue=pvalue,
                beats_baseline=beats,
                directional_accuracy_60d=item.get("direction_hit_rate"),
                n_validation=item.get("n_validation"),
                verdict_ja=_verdict_ja(beats_baseline=beats, dm_pvalue=pvalue),
            )
        )
    # ベースライン行を必ず含める
    spot = (raw.get("reference") or {}).get("value") or (raw.get("official") or {}).get("value")
    if spot is not None:
        forecasts.insert(
            0,
            FxForecast(
                horizon_days=5,
                horizon="H5",
                label_ja="5営業日",
                model_id="random_walk",
                point=float(spot),
                ci_lo_80=float(spot) * 0.98,
                ci_hi_80=float(spot) * 1.02,
                is_baseline=True,
                beats_baseline=False,
                verdict_ja="ベースライン（前日値をそのまま予測）。",
            ),
        )
    comparison = []
    for row in raw.get("model_comparison") or []:
        comparison.append(
            ModelComparisonRow(
                model_id=str(row.get("model")),
                is_baseline=bool(row.get("is_baseline")),
                rmse=row.get("rmse"),
                mae=row.get("mae"),
                direction_hit_rate=row.get("direction_hit_rate"),
                n=row.get("n"),
                dm_p_value=row.get("dm_p_value"),
                verdict_ja=row.get("verdict_ja"),
            )
        )
    vol = raw.get("volatility") or {}
    rd = raw.get("rate_differential") or {}
    official = raw.get("official") or {}
    reference = raw.get("reference") or {}
    return FxDetail(
        pair=pair,
        as_of=as_date(raw.get("as_of")) or state.as_of,
        spot=reference.get("value") or official.get("value"),
        official=FxQuote(
            value=float(official["value"]),
            as_of=as_date(official.get("as_of")) or state.as_of,
            source=str(official.get("source") or "fred"),
        )
        if official.get("value") is not None
        else None,
        reference=FxQuote(
            value=float(reference["value"]),
            as_of=as_utc(reference.get("as_of")) or state.as_of,
            source=str(reference.get("source") or "yfinance"),
            change_pct=reference.get("change_pct"),
            change_abs=reference.get("change_abs"),
            delay_minutes=reference.get("delay_minutes"),
        )
        if reference.get("value") is not None
        else None,
        verdict_ja=str(raw.get("verdict_ja") or _verdict_ja(beats_baseline=False, dm_pvalue=dm.get("p_value"))),
        verdict_status=str(raw.get("verdict_status") or "no_edge"),
        diebold_mariano=DieboldMariano(
            stat=dm.get("stat"),
            p_value=dm.get("p_value"),
            n_validation=dm.get("n_validation"),
            variance=dm.get("variance"),
            hac_lags=dm.get("hac_lags"),
        ),
        baseline_rmse=raw.get("baseline_rmse"),
        model_rmse=raw.get("model_rmse"),
        forecasts=forecasts,
        model_comparison=comparison,
        vol_forecast=FxVolForecast(
            garch_vol_20d_ann=vol.get("garch_forecast_20d"),
            realized_vol_20d=vol.get("realized_20d"),
            realized_vol_60d=vol.get("realized_60d"),
            persistence=vol.get("persistence"),
            converged=vol.get("converged"),
            regime_ja=vol.get("regime_ja"),
        ),
        cointegration=Cointegration(
            tested_pairs=["log_usdjpy", "rate_diff_10y"],
            rank=0,
            detected=False,
            note_ja="直近5年では共和分関係が検出されないため、VECMは参考扱いです。",
        ),
        rate_differential=RateDifferential(
            us_10y=rd.get("us_10y"),
            jp_10y=rd.get("jp_10y"),
            diff=rd.get("spread_10y"),
            us_2y=rd.get("us_2y"),
            jp_2y=rd.get("jp_2y"),
            diff_2y=rd.get("spread_2y"),
            correlation_1y=rd.get("correlation_1y"),
        ),
    )


@router.get("/fx/{pair}", response_model=Envelope[FxDetail])
def get_fx(
    pair: str,
    as_of: str | None = None,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[FxDetail]:
    pair = pair.upper()
    seeded = _fx_from_seed(state, pair)
    if seeded:
        return wrap(state, seeded, as_of=seeded.as_of)
    rows = state.duck.get_fx_forecasts(pair, as_of=as_date(as_of) if as_of else None)
    if not rows:
        raise not_found(f"為替ペア {pair} の予測がありません。")
    forecasts = []
    for r in rows:
        beats = r.get("beats_baseline")
        forecasts.append(
            FxForecast(
                horizon_days=int(r["horizon_days"]),
                model_id=r["model_id"],
                point=float(r["point_forecast"]),
                ci_lo_80=float(r["ci_lo_80"]),
                ci_hi_80=float(r["ci_hi_80"]),
                ci_lo_95=r.get("ci_lo_95"),
                ci_hi_95=r.get("ci_hi_95"),
                is_baseline=bool(r.get("is_baseline")),
                dm_statistic=r.get("dm_statistic"),
                dm_pvalue=r.get("dm_pvalue"),
                beats_baseline=beats,
                rmse_oos_60d=r.get("rmse_oos_60d"),
                baseline_rmse_oos_60d=r.get("baseline_rmse_oos_60d"),
                directional_accuracy_60d=r.get("directional_accuracy_60d"),
                n_validation=r.get("n_validation"),
                verdict_ja=_verdict_ja(beats_baseline=beats, dm_pvalue=r.get("dm_pvalue")),
            )
        )
    day = as_date(as_of) or as_date(rows[0].get("as_of")) or state.as_of
    spot = next((f.point for f in forecasts if f.is_baseline), forecasts[0].point)
    return wrap(
        state,
        FxDetail(
            pair=pair,
            as_of=day,
            spot=spot,
            verdict_ja=_verdict_ja(beats_baseline=False, dm_pvalue=None),
            verdict_status="no_edge",
            forecasts=forecasts,
        ),
        as_of=day,
    )


@router.get("/fx/{pair}/history", response_model=Envelope[FxHistory])
def get_fx_history(
    pair: str,
    range: str = Query(default="5y"),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[FxHistory]:
    pair = pair.upper()
    series_id = "DEXJPUS" if pair in {"USDJPY", "USD/JPY"} else pair
    start = parse_range_start(range, as_of=state.as_of)
    rows = state.duck.get_macro_as_of(series_id, as_of=state.as_of, limit=2000)
    points = [
        FxHistoryPoint(date=as_date(r["observation_date"]) or state.as_of, value=float(r["value"]))
        for r in reversed(rows)
        if r.get("value") is not None and (as_date(r["observation_date"]) or start) >= start
    ]
    if not points:
        for item in (state.payload.get("fx") or {}).get("history_sample") or []:
            points.append(FxHistoryPoint(date=as_date(item["date"]) or state.as_of, value=float(item["value"])))
    return wrap(
        state,
        FxHistory(pair=pair, range=range, source="fred", points=points),
    )


@router.get("/macro/series", response_model=Envelope[MacroSeriesResponse])
def get_macro_series(
    ids: str = Query(description="カンマ区切りの series_id"),
    range: str = Query(default="5y"),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[MacroSeriesResponse]:
    series_ids = [s.strip() for s in ids.split(",") if s.strip()]
    start = parse_range_start(range, as_of=state.as_of)
    out: list[MacroSeries] = []
    seed_index = {s["id"]: s for s in state.payload.get("macro_series") or []}
    for sid in series_ids:
        rows = state.duck.get_macro_as_of(sid, as_of=state.as_of, limit=2000)
        points = [
            MacroPoint(
                observation_date=as_date(r["observation_date"]) or state.as_of,
                value=r.get("value"),
                vintage_date=as_date(r.get("vintage_date")),
            )
            for r in reversed(rows)
            if (as_date(r.get("observation_date")) or start) >= start
        ]
        seed = seed_index.get(sid) or {}
        latest = points[-1] if points else None
        out.append(
            MacroSeries(
                series_id=sid,
                label_ja=seed.get("label_ja") or (rows[0].get("label_ja") if rows else None),
                unit=seed.get("unit") or (rows[0].get("unit") if rows else None),
                frequency=rows[0].get("frequency") if rows else None,
                latest=seed.get("latest") if not points else (latest.value if latest else None),
                change_mom=seed.get("change_mom"),
                as_of=as_date(seed.get("as_of")) or (latest.observation_date if latest else None),
                vintage_date=as_date(seed.get("vintage_date")) or (latest.vintage_date if latest else None),
                revised=bool(seed.get("revised")),
                revision_note_ja=seed.get("revision_note_ja"),
                points=points,
            )
        )
    return wrap(state, MacroSeriesResponse(range=range, series=out))


@router.get("/macro/rate-differential", response_model=Envelope[RateDifferentialResponse])
def get_rate_differential(
    range: str = Query(default="5y"),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[RateDifferentialResponse]:
    fx = _fx_from_seed(state, "USDJPY")
    current = fx.rate_differential if fx else None
    us = state.duck.get_macro_as_of("DGS10", as_of=state.as_of, limit=400)
    jp = state.duck.get_macro_as_of("IRLTLT01JPM156N", as_of=state.as_of, limit=400)
    dex = state.duck.get_macro_as_of("DEXJPUS", as_of=state.as_of, limit=400)
    us_map = {as_date(r["observation_date"]): r.get("value") for r in us}
    jp_map = {as_date(r["observation_date"]): r.get("value") for r in jp}
    dex_map = {as_date(r["observation_date"]): r.get("value") for r in dex}
    dates = sorted(set(us_map) & set(dex_map))
    points = []
    for day in dates[-400:]:
        us_v = us_map.get(day)
        jp_v = jp_map.get(day)
        spread = (us_v - jp_v) if us_v is not None and jp_v is not None else us_v
        points.append(
            RateDifferentialPoint(date=day, spread_10y=spread, usdjpy=dex_map.get(day))  # type: ignore[arg-type]
        )
    return wrap(
        state,
        RateDifferentialResponse(
            range=range,
            current=current,
            correlation_1y=current.correlation_1y if current else None,
            points=points,
        ),
    )
