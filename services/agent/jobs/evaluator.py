"""Evaluator: 実績確定・教訓・重み提案（docs/08-agent-loop.md §8）。

重みの適用はしない。提案だけを `factor_weights` に残す。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from packages.core.factors.calendar import TradingCalendar, next_business_day, shift_business_days
from packages.core.interfaces.storage import JobRunRepo, MemoryRecord, MemoryRepo, WarehouseRepo
from packages.core.llm.errors import CostCapExceeded, KillSwitchActive
from packages.core.llm.prompts import render_prompt
from packages.core.llm.router import LLMRouter
from packages.core.llm.schemas import EvaluatorOutput, Lesson
from services.agent.deps import begin_run, finish_run
from services.agent.types import JobResult, StepResult

ACTION_SIGN = {"watch": 1, "accumulate": 1, "reduce": -1, "avoid": -1}


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
            prices = warehouse.read_prices_daily(tickers=[ticker], start=entry_date, end=exit_date)
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
            bench_ret = 0.0
            excess = raw_ret - bench_ret
            expected_sign = ACTION_SIGN.get(str(r.get("action") or "watch"), 1)
            is_hit = (excess * expected_sign) > 0
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
                    "excess_return": excess,
                    "is_hit": bool(is_hit),
                    "max_favorable_excursion": None,
                    "max_adverse_excursion": None,
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
