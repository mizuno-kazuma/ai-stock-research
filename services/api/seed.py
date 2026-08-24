"""docs/ui/sample-data.json を DuckDB / SQLite に投入する。

    uv run python -m services.api.seed
    uv run python -m services.api.seed --reset   # 既存データを消して入れ直すわけではない（upsert）
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Any

from packages.core.config import Settings, get_settings
from packages.core.storage import DuckDBRepo, SQLiteRepo, init_all, utc_now_iso
from services.api.mapping import map_doc_source, map_doc_type
from services.api.util import as_date, as_iso, as_list, as_utc

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = REPO_ROOT / "docs" / "ui" / "sample-data.json"


def load_sample(path: Path | None = None) -> dict[str, Any]:
    target = path or SAMPLE_PATH
    return json.loads(target.read_text(encoding="utf-8"))


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC).replace(tzinfo=None)


def _source_doc_ids(row: dict[str, Any]) -> list[str]:
    ids = [str(x) for x in as_list(row.get("source_doc_ids"))]
    if ids:
        return ids
    return [str(c.get("doc_id")) for c in as_list(row.get("citations")) if c.get("doc_id")]


def _citations(row: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for item in as_list(row.get("citations")):
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "doc_id": str(item.get("doc_id") or ""),
                "page": item.get("page"),
                "quote": str(item.get("quote") or ""),
            }
        )
    return out


def seed_duck(duck: DuckDBRepo, payload: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    securities: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add_sec(ticker: str, market: str, **extra: Any) -> None:
        key = (ticker, market)
        if key in seen:
            return
        seen.add(key)
        securities.append(
            {
                "ticker": ticker,
                "market": market,
                "name_local": extra.get("name_local") or ticker,
                "name_en": extra.get("name_en"),
                "sector_code": extra.get("sector_code"),
                "sector_name": extra.get("sector_name"),
                "currency": extra.get("currency") or ("JPY" if market == "JP" else "USD"),
                "trading_unit": extra.get("trading_unit"),
                "is_active": True,
                "valid_from": dt.date(2020, 1, 1),
            }
        )

    for rec in payload.get("recommendations") or []:
        add_sec(
            rec["ticker"],
            rec["market"],
            name_local=rec.get("name_local"),
            name_en=rec.get("name_en"),
            sector_code=rec.get("sector_code"),
            sector_name=rec.get("sector_name"),
        )
    for item in payload.get("watchlist") or []:
        add_sec(item["ticker"], item["market"], name_local=item.get("name_local"))
    for key, detail in (payload.get("stock_detail") or {}).items():
        add_sec(
            detail["ticker"],
            detail["market"],
            name_local=detail.get("name_local"),
            name_en=detail.get("name_en"),
            sector_code=detail.get("sector_code"),
            sector_name=detail.get("sector_name"),
            trading_unit=detail.get("trading_unit"),
        )
    for row in (payload.get("screener") or {}).get("rows") or []:
        add_sec(row["ticker"], "JP", name_local=row.get("name_local"), sector_name=row.get("sector_name"))
    for peer in ((payload.get("peers") or {}).get("JP:7203") or []):
        add_sec(peer["ticker"], "JP", name_local=peer.get("name_local"))
    counts["securities"] = duck.upsert_securities(securities)

    rec_rows = []
    for rec in payload.get("recommendations") or []:
        fs = dict(rec.get("factor_scores") or {})
        if "lowvol" not in fs and "volatility" in fs:
            fs["lowvol"] = fs.get("volatility")
        rec_rows.append(
            {
                "rec_id": rec["rec_id"],
                "as_of": as_date(rec.get("as_of")),
                "ticker": rec["ticker"],
                "market": rec["market"],
                "action": rec["action"],
                "horizon": rec["horizon"],
                "conviction": rec["conviction"],
                "conviction_score": rec["conviction_score"],
                "thesis_ja": rec["thesis_ja"],
                "bear_case_ja": rec["bear_case_ja"],
                "invalidation_ja": rec["invalidation_ja"],
                "reason_codes": rec.get("reason_codes") or ["MODEL_LOW_CONFIDENCE"],
                "entry_ref_price": rec.get("entry_ref_price"),
                "entry_ref_source": rec.get("entry_ref_source"),
                "entry_ref_note_ja": rec.get("entry_ref_note_ja"),
                "stop_ref_price": rec.get("stop_ref_price"),
                "target_ref_price": rec.get("target_ref_price"),
                "currency": "JPY" if rec.get("market") == "JP" else "USD",
                "expected_ret": rec.get("expected_ret"),
                "expected_ret_lo": rec.get("expected_ret_lo"),
                "expected_ret_hi": rec.get("expected_ret_hi"),
                "hit_rate_prior": rec.get("hit_rate_prior"),
                "n_prior_samples": rec.get("n_prior_samples"),
                "quant_score": rec.get("quant_score"),
                "qual_score": rec.get("qual_score"),
                "total_score": rec.get("total_score"),
                "ml_pred": rec.get("ml_pred"),
                "factor_scores": fs or None,
                "source_doc_ids": _source_doc_ids(rec),
                "citations": _citations(rec),
                "data_freshness": rec.get("data_freshness") or [],
                "critic_verdict": rec.get("critic_verdict"),
                "critic_notes_ja": rec.get("critic_notes_ja"),
                "memory_ids_used": [str(x) for x in as_list(rec.get("memory_ids_used"))],
                "flags": rec.get("flags") or [],
                "generated_at": (lambda g: g.replace(tzinfo=None) if g else _now())(
                    as_utc(rec.get("generated_at"))
                ),
            }
        )
    try:
        counts["recommendations"] = duck.insert_recommendations(rec_rows)
    except Exception:
        logger.exception("推奨の投入に失敗したので1件ずつ入れます")
        ok = 0
        for row in rec_rows:
            try:
                duck.insert_recommendations([row])
                ok += 1
            except Exception:
                logger.exception("skip rec %s", row.get("rec_id"))
        counts["recommendations"] = ok

    price_daily: list[dict[str, Any]] = []
    price_live: list[dict[str, Any]] = []
    for key, block in (payload.get("prices") or {}).items():
        market, ticker = key.split(":", 1)
        research = block.get("research") or {}
        for bar in research.get("sample") or []:
            price_daily.append(
                {
                    "ticker": ticker,
                    "market": market,
                    "trade_date": as_date(bar["date"]),
                    "open": bar.get("open"),
                    "high": bar.get("high"),
                    "low": bar.get("low"),
                    "close": bar.get("close"),
                    "volume": bar.get("volume"),
                    "adj_close": bar.get("close"),
                    "currency": "JPY" if market == "JP" else "USD",
                    "source": research.get("source") or "jquants",
                }
            )
        live = block.get("live") or {}
        for bar in live.get("sample") or []:
            price_live.append(
                {
                    "ticker": ticker,
                    "market": market,
                    "trade_date": as_date(bar["date"]),
                    "open": bar.get("open"),
                    "high": bar.get("high"),
                    "low": bar.get("low"),
                    "close": bar.get("close"),
                    "volume": bar.get("volume"),
                    "currency": "JPY" if market == "JP" else "USD",
                    "source": live.get("source") or "yfinance",
                    "is_delayed": True,
                    "delay_note": "15分遅延",
                    "quoted_at": live.get("latest_as_of"),
                }
            )
    counts["prices_daily"] = duck.upsert_prices_daily(price_daily)
    counts["prices_live"] = duck.upsert_prices_live(price_live)

    docs = []
    for item in payload.get("filings") or []:
        docs.append(
            {
                "doc_id": item["doc_id"],
                "ticker": item.get("ticker"),
                "market": item.get("market") or "JP",
                "source": map_doc_source(item.get("source")),
                "doc_type": map_doc_type(item.get("doc_type")),
                "title": item.get("title") or item["doc_id"],
                "filed_at": item.get("filed_at"),
                "source_url": f"https://example.invalid/docs/{item['doc_id']}",
                "page_count": item.get("pages"),
                "byte_size": item.get("bytes"),
            }
        )
    counts["documents"] = duck.upsert_documents(docs)

    summary = payload.get("filing_summary") or {}
    if summary.get("doc_id") and summary.get("citations"):
        counts["document_summaries"] = duck.upsert_document_summaries(
            [
                {
                    "doc_id": summary["doc_id"],
                    "summary_version": summary.get("summary_version") or 1,
                    "model_id": summary.get("model") or "gemini-flash",
                    "prompt_hash": summary.get("prompt_hash") or "seed",
                    "input_hash": "seed",
                    "headline_ja": summary.get("headline_ja"),
                    "summary_ja": summary.get("headline_ja") or "",
                    "key_points": summary.get("key_points_ja") or [],
                    "risk_factors": summary.get("risk_factors_ja") or [],
                    "guidance_tone": summary.get("tone"),
                    "tone_rationale_ja": summary.get("tone_rationale_ja"),
                    "citations": [
                        {"page": c.get("page"), "quote": c.get("quote")}
                        for c in summary.get("citations") or []
                    ],
                    "input_tokens": summary.get("input_tokens"),
                    "output_tokens": summary.get("output_tokens"),
                    "cost_usd": summary.get("cost_usd"),
                    "computed_at": _now(),
                }
            ]
        )

    fin_rows = []
    for key, block in (payload.get("financials") or {}).items():
        market, ticker = key.split(":", 1)
        for i, period in enumerate(block.get("periods") or []):
            fp = str(period.get("fiscal_period") or "")
            year = 2026
            if len(fp) >= 4 and fp[:4].isdigit():
                year = int(fp[:4])
            period_type = "annual" if "通期" in fp else "quarter"
            fin_rows.append(
                {
                    "ticker": ticker,
                    "market": market,
                    "period_end": as_date(period.get("filed_at")) or dt.date(year, 3, 31),
                    "fiscal_year": year,
                    "fiscal_period": fp or f"P{i}",
                    "period_type": period_type,
                    "filed_at": as_date(period.get("filed_at")),
                    "doc_id": period.get("source_doc_id"),
                    "revenue": period.get("revenue"),
                    "operating_income": period.get("operating_income"),
                    "net_income": period.get("net_income"),
                    "eps": period.get("eps"),
                    "operating_cf": period.get("free_cash_flow"),
                    "currency": "JPY" if market == "JP" else "USD",
                    "is_restated": bool(period.get("restated") or period.get("is_restated")),
                    "source": "edinet" if market == "JP" else "edgar",
                }
            )
    counts["financials"] = duck.upsert_financials(fin_rows)

    scores = []
    as_of = as_date((payload.get("screener") or {}).get("as_of")) or dt.date(2026, 8, 22)
    for row in (payload.get("screener") or {}).get("rows") or []:
        scores.append(
            {
                "ticker": row["ticker"],
                "market": "JP",
                "as_of": as_of,
                "quant_score": row.get("total_score"),
                "total_score": row.get("total_score"),
                "weight_set_id": "ws_20260701_a",
                "feature_version": "v3",
                "computed_at": _now(),
            }
        )
    counts["scores_daily"] = duck.upsert_scores_daily(scores)

    features = []
    for key, block in (payload.get("factors") or {}).items():
        market, ticker = key.split(":", 1)
        features.append(
            {
                "ticker": ticker,
                "market": market,
                "as_of": as_date(block.get("as_of")) or as_of,
                "currency": "JPY" if market == "JP" else "USD",
                "feature_version": block.get("feature_version") or "v3",
                "n_missing": 0,
                "computed_at": _now(),
            }
        )
    counts["features_daily"] = duck.upsert_features_daily(features)

    fx_rows = []
    fx = payload.get("fx") or {}
    pair = fx.get("pair") or "USDJPY"
    fx_as_of = as_date(fx.get("as_of")) or as_of
    horizon_days = {"H5": 5, "H20": 20, "H60": 60}
    spot = (fx.get("reference") or {}).get("value") or (fx.get("official") or {}).get("value") or 152.0
    fx_rows.append(
        {
            "pair": pair,
            "as_of": fx_as_of,
            "horizon_days": 5,
            "model_id": "random_walk",
            "point_forecast": float(spot),
            "ci_lo_80": float(spot) * 0.98,
            "ci_hi_80": float(spot) * 1.02,
            "ci_lo_95": float(spot) * 0.96,
            "ci_hi_95": float(spot) * 1.04,
            "is_baseline": True,
            "beats_baseline": False,
            "computed_at": _now(),
        }
    )
    for item in fx.get("forecasts") or []:
        fx_rows.append(
            {
                "pair": pair,
                "as_of": fx_as_of,
                "horizon_days": horizon_days.get(item.get("horizon") or "", 20),
                "model_id": str(item.get("model") or "arimax"),
                "point_forecast": item.get("median"),
                "ci_lo_80": item.get("lo80"),
                "ci_hi_80": item.get("hi80"),
                "ci_lo_95": item.get("lo95") or item.get("lo80"),
                "ci_hi_95": item.get("hi95") or item.get("hi80"),
                "is_baseline": False,
                "dm_pvalue": item.get("p_value"),
                "beats_baseline": bool(item.get("beats_baseline")),
                "directional_accuracy_60d": item.get("direction_hit_rate"),
                "n_validation": item.get("n_validation"),
                "computed_at": _now(),
            }
        )
    counts["fx_forecasts"] = duck.upsert_fx_forecasts(fx_rows)

    macro = []
    for s in payload.get("macro_series") or []:
        day = as_date(s.get("as_of")) or as_of
        vintage = as_date(s.get("vintage_date")) or day
        macro.append(
            {
                "series_id": s["id"],
                "observation_date": day,
                "vintage_date": vintage,
                "value": s.get("latest"),
                "unit": s.get("unit"),
                "label_ja": s.get("label_ja"),
                "source": "fred",
            }
        )
    for item in fx.get("history_sample") or []:
        day = as_date(item["date"])
        macro.append(
            {
                "series_id": "DEXJPUS",
                "observation_date": day,
                "vintage_date": day,
                "value": item.get("value"),
                "unit": "jpy",
                "label_ja": "ドル円",
                "source": "fred",
            }
        )
    counts["macro_series"] = duck.upsert_macro_series(macro)

    model_runs = []
    for row in payload.get("model_runs") or []:
        model_runs.append(
            {
                "run_id": row["run_id"],
                "model_kind": row.get("kind") or "ranker",
                "model_version": row.get("feature_version") or "v3",
                "market": row.get("market"),
                "horizon": row.get("horizon"),
                "train_start": as_date(row.get("period_start")),
                "train_end": as_date(row.get("period_end")),
                "cv_scheme": "purged_walk_forward",
                "purge_days": 20,
                "embargo_days": 5,
                "n_folds": len(row.get("fold_rank_ic") or []) or 8,
                "feature_version": row.get("feature_version") or "v3",
                "feature_list": ["rev_guidance_op_3m", "mom_12m_ex1m", "earnings_yield"],
                "input_snapshot_hash": "seed",
                "n_trials": row.get("n_trials") or 1,
                "fold_rank_ic": row.get("fold_rank_ic") or [],
                "fold_ic_std": row.get("fold_ic_std"),
                "started_at": _now(),
                "status": "success",
            }
        )
    counts["model_runs"] = duck.upsert_model_runs(model_runs)

    backtests = []
    for row in payload.get("backtests") or []:
        backtests.append(
            {
                **{k: v for k, v in row.items() if k != "dsr_p_value"},
                "dsr_pvalue": row.get("dsr_pvalue") or row.get("dsr_p_value"),
                "n_trials": row.get("n_trials") or 1,
                "period_start": as_date(row.get("period_start")),
                "period_end": as_date(row.get("period_end")),
                "run_at": _now(),
            }
        )
    counts["backtest_runs"] = duck.upsert_backtest_runs(backtests)
    return counts


def seed_sqlite(state: SQLiteRepo, payload: dict[str, Any]) -> dict[str, int]:
    from packages.core.storage.sqlite_repo import JobRun

    counts: dict[str, int] = {}
    settings = dict(payload.get("settings") or {})
    settings["seed.is_seed_data"] = True
    state.set_settings(settings)
    counts["settings"] = len(settings)

    # jobs
    n_jobs = 0
    with state.session() as s:
        for job in payload.get("jobs") or []:
            run_id = int(job["job_run_id"])
            existing = s.get(JobRun, run_id)
            checkpoint = job.get("checkpoint")
            metrics = job.get("metrics") or {}
            row = existing or JobRun(
                id=run_id,
                job_name=job["job_name"],
                trigger=job.get("trigger") or "schedule",
                status=job.get("status") or "success",
                started_at=as_iso(job.get("started_at")) or utc_now_iso(),
            )
            row.job_name = job["job_name"]
            row.trigger = job.get("trigger") or "schedule"
            row.status = job.get("status") or "success"
            row.started_at = as_iso(job.get("started_at")) or utc_now_iso()
            row.finished_at = as_iso(job.get("finished_at"))
            row.duration_sec = job.get("duration_sec")
            row.checkpoint = json.dumps(checkpoint, ensure_ascii=False) if checkpoint else None
            row.metrics = json.dumps(metrics, ensure_ascii=False) if metrics else None
            if existing is None:
                s.add(row)
            n_jobs += 1
    counts["job_runs"] = n_jobs

    n_alerts = 0
    for item in payload.get("alerts") or []:
        severity = item.get("severity") or "info"
        if severity == "danger":
            severity = "error"
        try:
            state.add_alert(
                alert_id=str(item["alert_id"]),
                severity=severity,
                category=item.get("category") or "data",
                title_ja=item.get("title_ja") or "",
                body_ja=item.get("link"),
            )
            if item.get("is_read"):
                state.mark_alert_read(str(item["alert_id"]))
            n_alerts += 1
        except Exception:
            logger.exception("alert skip %s", item.get("alert_id"))
    counts["alerts"] = n_alerts

    n_mem = 0
    for mem in payload.get("agent_memory") or []:
        state.upsert_agent_memory(
            memory_id=str(mem["memory_id"]),
            scope=mem.get("scope") or "global",
            scope_value=mem.get("scope_value"),
            category=mem.get("category") or "lesson",
            lesson_ja=mem.get("lesson_ja") or "",
            evidence_ja=mem.get("evidence_ja") or "",
            derived_from=[],
            n_observations=int(mem.get("n_evidence") or 0),
            confidence=0.4 if mem.get("harmful_flag") else 0.75,
            is_active=bool(mem.get("is_active", True)),
        )
        n_mem += 1
    counts["agent_memory"] = n_mem

    fw = payload.get("factor_weights") or {}
    n_fw = 0
    for key, row in (("active", fw.get("active")), ("proposed", fw.get("proposed"))):
        if not row:
            continue
        weights = dict(row.get("weights") or {})
        state.upsert_weight_set(
            weight_set_id=row["weight_set_id"],
            market=fw.get("market") or "JP",
            horizon=fw.get("horizon") or "H20",
            weights=weights,
            fitted_from="2026-02-01",
            fitted_to="2026-08-01",
            fit_method=row.get("fit_method") or "ridge",
            is_active=key == "active",
            created_by="seed",
            activated_at=as_iso(row.get("activated_at")) if key == "active" else None,
        )
        n_fw += 1
    for hist in fw.get("history") or []:
        if hist.get("weight_set_id") == (fw.get("active") or {}).get("weight_set_id"):
            continue
        state.upsert_weight_set(
            weight_set_id=hist["weight_set_id"],
            market=fw.get("market") or "JP",
            horizon=fw.get("horizon") or "H20",
            weights={"value": 0.25, "quality": 0.25, "momentum": 0.25, "revision": 0.25},
            fitted_from="2026-01-01",
            fitted_to="2026-04-01",
            fit_method="ridge",
            is_active=False,
            created_by="seed",
        )
        n_fw += 1
    counts["factor_weights"] = n_fw

    n_wl = 0
    for item in payload.get("watchlist") or []:
        state.add_to_watchlist(item["ticker"], item["market"], note_ja=None)
        n_wl += 1
    counts["watchlist"] = n_wl

    n_pos = 0
    for pos in payload.get("positions") or []:
        opened = "2026-01-01T00:00:00Z"
        state.upsert_position(
            ticker=pos["ticker"],
            market=pos["market"],
            account_type="特定",
            quantity=pos["quantity"],
            avg_cost=pos["avg_cost"],
            currency="JPY" if pos["market"] == "JP" else "USD",
            opened_at=opened,
            is_open=True,
        )
        n_pos += 1
    counts["positions"] = n_pos

    n_tr = 0
    for tr in payload.get("trades") or []:
        try:
            state.insert_trade(
                trade_id=str(tr["trade_id"]),
                ticker=tr["ticker"],
                market=tr["market"],
                side=tr["side"],
                quantity=tr["quantity"],
                price=tr["price"],
                fee=tr.get("fee") or 0,
                currency=tr.get("currency") or "JPY",
                executed_at=as_iso(tr.get("executed_at")) or utc_now_iso(),
                broker=tr.get("broker"),
                account_type=tr.get("account_type"),
                linked_rec_id=tr.get("linked_rec_id"),
                thesis_ja=tr.get("thesis_ja"),
                emotion_tag=tr.get("emotion_tag"),
                exit_plan_ja=tr.get("exit_plan_ja"),
            )
            n_tr += 1
        except Exception:
            logger.exception("trade skip %s", tr.get("trade_id"))
    counts["trades"] = n_tr

    cost = payload.get("llm_cost") or {}
    today = dt.date(2026, 8, 22).isoformat()
    month = "2026-08"
    state.upsert_cost_budget("daily", today, cap_usd=float(cost.get("daily_cap_usd") or 1.5), spent_usd=float(cost.get("today_usd") or 0))
    state.upsert_cost_budget("monthly", month, cap_usd=float(cost.get("monthly_cap_usd") or 20), spent_usd=float(cost.get("month_usd") or 0))
    n_llm = 0
    for i, call in enumerate(cost.get("recent_calls") or []):
        try:
            state.record_llm_call(
                call_id=f"seed-{i}",
                tier="default",
                model_id=call.get("model") or "unknown",
                purpose=call.get("purpose") or "doc_summary",
                input_tokens=int(call.get("input_tokens") or 0),
                output_tokens=int(call.get("output_tokens") or 0),
                cost_usd=float(call.get("cost_usd") or 0),
                status=call.get("status") or "success",
                called_at=as_iso(call.get("at")) or utc_now_iso(),
                was_cache_hit=bool(call.get("cache_hit")),
                error_message=call.get("error_ja"),
            )
            n_llm += 1
        except Exception:
            logger.exception("llm_call skip")
    counts["llm_calls"] = n_llm
    return counts


def seed_all(
    duck: DuckDBRepo,
    state: SQLiteRepo,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = payload or load_sample()
    duck_counts = seed_duck(duck, data)
    sqlite_counts = seed_sqlite(state, data)
    return {"duckdb": duck_counts, "sqlite": sqlite_counts, "as_of": (data.get("_meta") or {}).get("as_of")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="sample-data.json を DB に投入する")
    parser.add_argument("--sample", type=Path, default=SAMPLE_PATH)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    settings.ensure_directories()
    init_all(settings)
    payload = load_sample(args.sample)
    with DuckDBRepo.open(settings, read_only=False) as duck, SQLiteRepo.open(settings) as state:
        result = seed_all(duck, state, payload)
    if (sys.stdout.encoding or "").lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
