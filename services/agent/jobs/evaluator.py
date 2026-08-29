"""Evaluator: 実績確定・教訓・重み提案（docs/08-agent-loop.md §8）。

重みの適用はしない。提案だけを `factor_weights` に残す。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from packages.core.factors.calendar import TradingCalendar
from packages.core.factors.factor_config import DEFAULT_GROUP_WEIGHTS
from packages.core.interfaces.storage import JobRunRepo, MemoryRecord, MemoryRepo, WarehouseRepo
from packages.core.llm.errors import CostCapExceeded, KillSwitchActive
from packages.core.llm.prompts import render_prompt
from packages.core.llm.router import LLMRouter
from packages.core.llm.schemas import EvaluatorOutput, Lesson
from services.agent.deps import begin_run, finish_run
from services.agent.types import JobResult, StepResult

ACTION_SIGN = {"watch": 1, "accumulate": 1, "reduce": -1, "avoid": -1}
GROUP_Z_COLS = {
    "value": "value_z",
    "momentum": "momentum_z",
    "quality": "quality_z",
    "growth": "growth_z",
    "lowvol": "lowvol_z",
    "revision": "revision_z",
}
BENCHMARK_TICKERS = {
    "JP": ("TOPIX", "1306", "1306.T", "^TOPX"),
    "US": ("SPX", "SPY", "^GSPC"),
}


def evaluate_outcomes(
    as_of: date,
    *,
    warehouse: WarehouseRepo,
    calendar: TradingCalendar | None = None,
) -> list[dict[str, Any]]:
    """as_of 時点で horizon に到達した推奨を評価する。エントリーは翌営業日始値。"""
    cal = calendar or TradingCalendar()
    outcomes: list[dict[str, Any]] = []
    for horizon, days in (("H5", 5), ("H20", 20)):
        target_as_of = cal.shift(as_of, -(days + 1))
        recs = warehouse.get_recommendations(
            as_of=target_as_of, horizon=horizon, critic_verdict="approved"
        )
        for r in recs:
            market = r.get("market") or "JP"
            ticker = str(r["ticker"])
            entry_date = cal.next_business_day(r["as_of"])
            exit_date = cal.shift(entry_date, days)
            bench_tickers = list(BENCHMARK_TICKERS.get(market, ()))
            prices = warehouse.read_prices_daily(
                tickers=[ticker, *bench_tickers], start=entry_date, end=exit_date
            )
            entry = _open_on(prices, ticker, entry_date)
            exit_ = _open_on(prices, ticker, exit_date)
            if entry is None or exit_ is None:
                warehouse.record_data_gap(
                    source="evaluator",
                    entity=ticker,
                    gap_start=entry_date,
                    gap_end=exit_date,
                    reason="price missing",
                )
                continue
            raw_ret = exit_ / entry - 1.0
            bench_ret, bench_ticker = _benchmark_return(
                prices, market, entry_date, exit_date
            )
            excess = raw_ret - bench_ret
            expected_sign = ACTION_SIGN.get(str(r.get("action") or "watch"), 1)
            is_hit = (excess * expected_sign) > 0
            mfe, mae = _excursions(
                prices, ticker, entry_date, exit_date, entry, expected_sign
            )
            outcomes.append(
                {
                    "rec_id": r["rec_id"],
                    "horizon": horizon,
                    "ticker": ticker,
                    "market": market,
                    "as_of": r["as_of"],
                    "entry_date": entry_date,
                    "exit_date": exit_date,
                    "entry_price": entry,
                    "exit_price": exit_,
                    "raw_return": raw_ret,
                    "benchmark_return": bench_ret,
                    "benchmark_ticker": bench_ticker,
                    "excess_return": excess,
                    "is_hit": bool(is_hit),
                    "max_favorable_excursion": mfe,
                    "max_adverse_excursion": mae,
                }
            )
    if outcomes:
        warehouse.upsert_recommendation_outcomes(outcomes)
    return outcomes


def update_memory(
    new_lessons: list[Lesson], existing: list[MemoryRecord]
) -> dict[str, list[Any]]:
    added: list[Lesson] = []
    superseded: list[tuple[str, Lesson]] = []
    deactivated: list[str] = []
    for lesson in new_lessons:
        if lesson.n_observations < 10:
            continue
        dup = _find_similar(existing, lesson, threshold=0.85)
        if dup:
            if lesson.n_observations > dup.n_observations:
                superseded.append((dup.memory_id, lesson))
            continue
        added.append(lesson)
    for m in existing:
        if m.hit_rate_after is not None and m.hit_rate_before is not None:
            if m.hit_rate_after < m.hit_rate_before - 0.05 and m.use_count >= 20:
                deactivated.append(m.memory_id)
    return {"added": added, "superseded": superseded, "deactivated": deactivated}


def propose_factor_weights(
    group_z: pd.DataFrame,
    excess: pd.Series,
    current: dict[str, float],
    *,
    blend: float = 0.5,
    ridge: float = 1.0,
) -> dict[str, float] | None:
    """非負制約の Ridge。サンプル 100 件未満なら提案しない。自動適用しない。"""
    if len(excess.dropna()) < 100:
        return None
    cols = [c for c in current if c in group_z.columns]
    if not cols:
        return None
    X = group_z[cols].apply(pd.to_numeric, errors="coerce").fillna(0.0).to_numpy()
    y = pd.to_numeric(excess, errors="coerce").fillna(0.0).to_numpy()
    xtx = X.T @ X + ridge * np.eye(len(cols))
    xty = X.T @ y
    try:
        beta = np.linalg.solve(xtx, xty)
    except np.linalg.LinAlgError:
        return None
    beta = np.clip(beta, 0.0, None)
    if float(beta.sum()) <= 0:
        return None
    beta = beta / beta.sum()
    proposed = {}
    for i, col in enumerate(cols):
        proposed[col] = float(blend * current[col] + (1.0 - blend) * beta[i])
        if abs(proposed[col] - current[col]) > 0.10:
            # 急激な変化は過剰適合の兆候。ブレンドをさらに寄せる。
            proposed[col] = float(0.8 * current[col] + 0.2 * beta[i])
    s = sum(proposed.values()) or 1.0
    return {k: v / s for k, v in proposed.items()}


def evaluator(
    market: str,
    as_of: date,
    *,
    state: JobRunRepo,
    warehouse: WarehouseRepo,
    memory: MemoryRepo | None = None,
    router: LLMRouter | None = None,
    trigger: str = "schedule",
    parent_run_id: int | None = None,
) -> JobResult:
    run_id = begin_run(
        state, job_name="evaluator", market=market, trigger=trigger, parent_run_id=parent_run_id
    )
    outcomes = evaluate_outcomes(as_of, warehouse=warehouse)
    metrics: dict[str, Any] = {"n_outcomes": len(outcomes)}
    if outcomes:
        hits = [o["is_hit"] for o in outcomes]
        metrics["hit_rate"] = float(np.mean(hits))
        metrics["benchmark_missing"] = all(
            o.get("benchmark_ticker") is None for o in outcomes
        )
        by_conv: dict[str, list[bool]] = {}
        recs = {
            r["rec_id"]: r
            for r in warehouse.get_recommendations(market=market, critic_verdict="approved")
        }
        for o in outcomes:
            rec = recs.get(o["rec_id"]) or {}
            conv = str(rec.get("conviction") or "low")
            by_conv.setdefault(conv, []).append(bool(o["is_hit"]))
        metrics["hit_rate_by_conviction"] = {
            k: float(np.mean(v)) for k, v in by_conv.items() if v
        }
        # 確信度の単調性が崩れていたら caveat を残す。
        order = ["low", "medium", "high"]
        rates = [metrics["hit_rate_by_conviction"].get(k) for k in order]
        known = [(k, r) for k, r in zip(order, rates, strict=False) if r is not None]
        if len(known) >= 2:
            vals = [r for _, r in known]
            if any(vals[i] > vals[i + 1] + 1e-9 for i in range(len(vals) - 1)):
                metrics["conviction_not_monotonic"] = True

    _record_weight_proposal(
        as_of, market, outcomes, warehouse=warehouse, state=state, memory=memory, metrics=metrics
    )

    lessons: list[Lesson] = []
    if router is not None and len(outcomes) >= 10:
        try:
            existing = memory.list_memory() if memory is not None else []
            rendered = render_prompt(
                "evaluator.jinja",
                horizon="H20",
                n=len(outcomes),
                outcomes=outcomes,
                hit_rate=metrics.get("hit_rate"),
                hit_rate_by_conviction=metrics.get("hit_rate_by_conviction"),
                hit_rate_by_reason_code={},
                coverage_rate=None,
                existing_memory=existing,
            )
            resp = router.complete(
                tier="default",
                purpose="evaluator",
                messages=[{"role": "user", "content": rendered}],
                response_schema=EvaluatorOutput,
                job_run_id=run_id,
                prompt_name="evaluator.jinja",
                prompt_body=rendered,
            )
            if resp.parsed is not None:
                lessons = list(resp.parsed.lessons)
        except (CostCapExceeded, KillSwitchActive):
            metrics["llm_capped"] = True
        except Exception as exc:
            metrics["eval_llm_error"] = type(exc).__name__

    if memory is not None and lessons:
        existing = memory.list_memory(include_inactive=True)
        upd = update_memory(lessons, existing)
        for lesson in upd["added"]:
            memory.insert_memory(
                MemoryRecord(
                    memory_id=f"M{len(existing) + 1:04d}",
                    scope=lesson.scope,
                    category=lesson.category,
                    lesson_ja=lesson.lesson_ja,
                    evidence_ja=lesson.evidence_ja,
                    n_observations=lesson.n_observations,
                    confidence=lesson.confidence,
                    scope_value=lesson.scope_value,
                )
            )
        for mid in upd["deactivated"]:
            memory.update_memory(mid, {"is_active": False})
        metrics["memory_added"] = len(upd["added"])
        metrics["memory_deactivated"] = len(upd["deactivated"])

    status = "success"
    finish_run(state, run_id, status=status, metrics=metrics)
    return JobResult(
        job_name="evaluator",
        status=status,
        market=market,
        as_of=as_of,
        run_id=run_id,
        steps={"outcomes": StepResult(status=status)},
        metrics=metrics,
        outcomes=outcomes,
    )


def _open_on(prices: pd.DataFrame, ticker: str, on: date) -> float | None:
    if prices is None or prices.empty:
        return None
    work = prices.copy()
    if "trade_date" in work.columns:
        work["trade_date"] = pd.to_datetime(work["trade_date"]).dt.date
    if "ticker" in work.columns:
        work = work.loc[work["ticker"].astype(str) == ticker]
        work = work.loc[work["trade_date"] == on]
    if work.empty:
        return None
    col = "adj_open" if "adj_open" in work.columns else "open"
    val = pd.to_numeric(work.iloc[-1][col], errors="coerce")
    if pd.isna(val) or float(val) <= 0:
        return None
    return float(val)


def _benchmark_return(
    prices: pd.DataFrame, market: str, entry_date: date, exit_date: date
) -> tuple[float, str | None]:
    for ticker in BENCHMARK_TICKERS.get(market, ()):
        entry = _open_on(prices, ticker, entry_date)
        exit_ = _open_on(prices, ticker, exit_date)
        if entry is None or exit_ is None:
            continue
        return exit_ / entry - 1.0, ticker
    return 0.0, None


def _excursions(
    prices: pd.DataFrame,
    ticker: str,
    entry_date: date,
    exit_date: date,
    entry_price: float,
    expected_sign: int,
) -> tuple[float | None, float | None]:
    """保有期間中の最大含み益 (MFE) と最大含み損 (MAE)。符号は推奨方向。"""
    if prices is None or prices.empty or entry_price <= 0:
        return None, None
    work = prices.copy()
    work["trade_date"] = pd.to_datetime(work["trade_date"]).dt.date
    if "ticker" in work.columns:
        work = work.loc[work["ticker"].astype(str) == ticker]
    work = work.loc[(work["trade_date"] >= entry_date) & (work["trade_date"] <= exit_date)]
    if work.empty:
        return None, None
    high_col = next((c for c in ("adj_high", "high", "adj_close", "adj_open") if c in work.columns), None)
    low_col = next((c for c in ("adj_low", "low", "adj_close", "adj_open") if c in work.columns), None)
    if high_col is None or low_col is None:
        return None, None
    highs = pd.to_numeric(work[high_col], errors="coerce")
    lows = pd.to_numeric(work[low_col], errors="coerce")
    if expected_sign >= 0:
        fav = highs / entry_price - 1.0
        adv = lows / entry_price - 1.0
    else:
        fav = 1.0 - lows / entry_price
        adv = 1.0 - highs / entry_price
    fav = fav.dropna()
    adv = adv.dropna()
    mfe = float(fav.max()) if not fav.empty else None
    mae = float(adv.min()) if not adv.empty else None
    return mfe, mae


def _record_weight_proposal(
    as_of: date,
    market: str,
    outcomes: list[dict[str, Any]],
    *,
    warehouse: WarehouseRepo,
    state: JobRunRepo,
    memory: MemoryRepo | None,
    metrics: dict[str, Any],
) -> None:
    h20 = [o for o in outcomes if o.get("horizon") == "H20"]
    if len(h20) < 100:
        metrics["weight_proposal"] = "skipped_n"
        return
    current = _current_weights(state, memory, market)
    group_z, excess = _align_scores(warehouse, h20, market)
    proposed = propose_factor_weights(group_z, excess, current)
    if proposed is None:
        metrics["weight_proposal"] = "skipped_fit"
        return
    inserter = getattr(memory, "insert_factor_weights", None)
    if not callable(inserter):
        inserter = getattr(state, "insert_factor_weights", None)
    if not callable(inserter):
        metrics["weight_proposal"] = "skipped_repo"
        return
    dates = [o["as_of"] for o in h20 if o.get("as_of") is not None]
    weight_set_id = f"eval_{market}_H20_{as_of.isoformat()}"
    inserter(
        {
            "weight_set_id": weight_set_id,
            "market": market,
            "horizon": "H20",
            "weights": proposed,
            "fitted_from": str(min(dates)) if dates else str(as_of),
            "fitted_to": str(max(dates)) if dates else str(as_of),
            "fit_method": "ridge_nn",
            "is_active": False,
            "created_by": "evaluator",
        }
    )
    metrics["weight_proposal"] = "proposed"
    metrics["weight_set_id"] = weight_set_id


def _current_weights(state: JobRunRepo, memory: MemoryRepo | None, market: str) -> dict[str, float]:
    getter = getattr(memory, "get_active_factor_weights", None)
    if not callable(getter):
        getter = getattr(state, "get_active_factor_weights", None)
    row = getter(market=market, horizon="H20") if callable(getter) else None
    weights = row.get("weights") if isinstance(row, dict) else None
    if isinstance(weights, dict) and weights:
        return {str(k): float(v) for k, v in weights.items()}
    return dict(DEFAULT_GROUP_WEIGHTS.get(market, {}).get("H20") or DEFAULT_GROUP_WEIGHTS["JP"]["H20"])


def _align_scores(
    warehouse: WarehouseRepo, outcomes: list[dict[str, Any]], market: str
) -> tuple[pd.DataFrame, pd.Series]:
    from collections import defaultdict

    by_asof: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for item in outcomes:
        as_of = item.get("as_of")
        if as_of is None:
            continue
        by_asof[as_of].append(item)
    records: list[dict[str, Any]] = []
    excess: list[float] = []
    for as_of, group in by_asof.items():
        scores = warehouse.read_scores_daily(as_of=as_of, market=market)
        if scores is None or getattr(scores, "empty", True):
            continue
        frame = scores.copy()
        if "ticker" not in frame.columns:
            continue
        indexed = {str(row["ticker"]): row for row in frame.to_dict(orient="records")}
        for item in group:
            row = indexed.get(str(item["ticker"]))
            if row is None:
                continue
            records.append({group: row.get(col) for group, col in GROUP_Z_COLS.items()})
            excess.append(float(item.get("excess_return") or 0.0))
    return pd.DataFrame(records), pd.Series(excess, dtype=float)


def _find_similar(
    existing: list[MemoryRecord], lesson: Lesson, *, threshold: float
) -> MemoryRecord | None:
    from difflib import SequenceMatcher

    best = None
    best_s = 0.0
    for m in existing:
        if not m.is_active:
            continue
        s = SequenceMatcher(None, m.lesson_ja, lesson.lesson_ja).ratio()
        if s > best_s:
            best_s = s
            best = m
    return best if best_s >= threshold else None
