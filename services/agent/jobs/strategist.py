"""Strategist: 推奨カード生成（docs/08-agent-loop.md §6）。

LLM が止まっても定量スコアだけでカードを出す。不完全な推奨は破棄する。
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

import pandas as pd

from packages.core.factors.scoring import is_candidate, total_score
from packages.core.factors.screening import (
    MIN_PRIOR_SAMPLES,
    UniverseFilter,
    apply_risk_constraints,
    assign_reason_codes,
    compute_hit_rate_prior,
    conviction_from_score,
    determine_action,
)
from packages.core.interfaces.storage import JobRunRepo, MemoryRepo, WarehouseRepo
from packages.core.llm.errors import (
    CostCapExceeded,
    InvariantViolationError,
    KillSwitchActive,
)
from packages.core.llm.prompts import render_prompt
from packages.core.llm.router import LLMRouter
from packages.core.llm.schemas import Citation, ThesisOutput
from services.agent.checkpoint import with_checkpoint
from services.agent.deps import begin_run, finish_run
from services.agent.types import JobResult, StepResult

FALLBACK_BEAR = (
    "定量スコア上位だが、開示資料の定性分析が停止または不足しているため、"
    "バリュートラップと業績モメンタム剥落の両方を却下理由として残す。"
    "信頼区間が広く、母数不足なら確信度は低に固定する。"
)


def _force_conviction(raw: str, n_prior: int) -> str:
    if n_prior < MIN_PRIOR_SAMPLES:
        return "low"
    return raw


def _validate_rec(rec: dict[str, Any]) -> None:
    bear = (rec.get("bear_case_ja") or "").strip()
    if len(bear) < 20:
        raise InvariantViolationError("bear_case が短すぎます")
    if rec.get("expected_ret_lo") is None or rec.get("expected_ret_hi") is None:
        raise InvariantViolationError("confidence_interval がありません")
    if not rec.get("citations"):
        raise InvariantViolationError("citations が空です")
    if not (rec.get("invalidation_ja") or "").strip():
        raise InvariantViolationError("invalidation_ja が空です")


def build_recommendation(
    row: pd.Series,
    *,
    as_of: date,
    market: str,
    n_prior_samples: int,
    hit_rate_prior: float | None,
    thesis: ThesisOutput | None,
    memory_ids: list[str],
    source_doc_ids: list[str],
    data_freshness: list[dict[str, Any]],
) -> dict[str, Any]:
    action = determine_action(row, is_held=False) or "watch"
    conv_score = float(row.get("quant_score") or 50.0) / 100.0
    if thesis is not None:
        raw_conv = thesis.conviction
        thesis_ja = thesis.thesis_ja
        bear = thesis.bear_case_ja
        inval = thesis.invalidation_ja
        citations = [c.model_dump() for c in thesis.citations]
    else:
        raw_conv = "low"
        thesis_ja = (
            f"{row.get('ticker')} は定量スコア {row.get('quant_score')}、"
            f"ML予測 {row.get('ml_pred_h20')} "
            f"[{row.get('ml_pred_h20_lo')}, {row.get('ml_pred_h20_hi')}]。"
            "定性分析は本日停止または未実施。"
        )
        bear = FALLBACK_BEAR
        inval = "次期の会社予想が下方修正されたら見立てを破棄する。"
        citations = [
            Citation(
                doc_id="quant:scores_daily",
                page=None,
                quote="定量スコアとML予測区間に基づく自動生成カードです。",
            ).model_dump()
        ]
        if not source_doc_ids:
            source_doc_ids = ["quant:scores_daily"]
    level, _reasons = conviction_from_score(
        conv_score,
        n_prior_samples=n_prior_samples,
        realized_vol_60d=(
            float(row["realized_vol_60d"])
            if "realized_vol_60d" in row and pd.notna(row.get("realized_vol_60d"))
            else None
        ),
    )
    if thesis is not None:
        # LLM の conviction と規則側の厳しい方を取る。
        order = {"low": 0, "medium": 1, "high": 2}
        level = raw_conv if order[raw_conv] <= order[level] else level
    level = _force_conviction(level, n_prior_samples)
    rec = {
        "rec_id": str(uuid.uuid4()),
        "as_of": as_of,
        "market": market,
        "ticker": str(row.get("ticker")),
        "action": action,
        "horizon": "H20",
        "quant_score": row.get("quant_score"),
        "qual_score": row.get("qual_score"),
        "total_score": row.get("total_score"),
        "ml_pred_h20": row.get("ml_pred_h20"),
        "expected_ret": row.get("ml_pred_h20"),
        "expected_ret_lo": row.get("ml_pred_h20_lo"),
        "expected_ret_hi": row.get("ml_pred_h20_hi"),
        "thesis_ja": thesis_ja,
        "bear_case_ja": bear,
        "invalidation_ja": inval,
        "conviction": level,
        "n_prior_samples": n_prior_samples,
        "hit_rate_prior": hit_rate_prior,
        "reason_codes": row.get("reason_codes") or [],
        "citations": citations,
        "source_doc_ids": source_doc_ids,
        "memory_ids_used": memory_ids,
        "data_freshness": data_freshness,
        "critic_verdict": None,
        "entry_ref_source": "prices_daily",
    }
    _validate_rec(rec)
    return rec


def strategist(
    market: str,
    as_of: date,
    *,
    state: JobRunRepo,
    warehouse: WarehouseRepo,
    memory: MemoryRepo | None = None,
    router: LLMRouter | None = None,
    scores: pd.DataFrame | None = None,
    outcomes: pd.DataFrame | None = None,
    universe_filter: UniverseFilter | None = None,
    max_per_day: int = 10,
    trigger: str = "schedule",
    parent_run_id: int | None = None,
    researcher_qual: list[dict[str, Any]] | None = None,
) -> JobResult:
    run_id = begin_run(
        state, job_name="strategist", market=market, trigger=trigger, parent_run_id=parent_run_id
    )
    if scores is None:
        scores = warehouse.read_scores_daily(as_of=as_of, market=market)
    if scores is None or scores.empty:
        finish_run(state, run_id, status="failed", metrics={"reason": "no_scores"})
        return JobResult(
            job_name="strategist",
            status="failed",
            market=market,
            as_of=as_of,
            run_id=run_id,
            error="scores が空",
        )

    work = scores.copy()
    if researcher_qual:
        qmap = {r["ticker"]: r for r in researcher_qual}
        work["qual_score"] = work["ticker"].map(
            lambda t: (qmap.get(str(t)) or {}).get("score")
        )
        work["qual_confidence"] = work["ticker"].map(
            lambda t: (qmap.get(str(t)) or {}).get("confidence")
        )
        work["total_score"] = total_score(
            work["quant_score"], work["qual_score"], work["qual_confidence"]
        )

    filt = universe_filter or UniverseFilter(market=market)
    mask = filt.apply(work, as_of=as_of)
    work = work.loc[mask] if mask.any() else work
    cand_mask = work.apply(is_candidate, axis=1) if not work.empty else pd.Series(dtype=bool)
    candidates = work.loc[cand_mask] if cand_mask.any() else work.head(0)
    # 候補ゼロのときは定量上位から埋める（機能縮退。空で黙らない）。
    if candidates.empty and not work.empty:
        candidates = work.sort_values("total_score", ascending=False).head(max_per_day)
    candidates = apply_risk_constraints(candidates, max_per_day=max_per_day)

    freshness = []
    try:
        fresh = warehouse.read_data_freshness()
        if fresh is not None and not fresh.empty:
            freshness = fresh.to_dict(orient="records")
    except Exception:
        freshness = []

    recs: list[dict[str, Any]] = []
    llm_capped = False

    def process(ticker: str) -> None:
        nonlocal llm_capped
        row = candidates.loc[candidates["ticker"].astype(str) == ticker].iloc[0]
        reasons = assign_reason_codes(row)
        row = row.copy()
        row["reason_codes"] = reasons
        prior = compute_hit_rate_prior(
            outcomes if outcomes is not None else pd.DataFrame(),
            market=market,
            horizon="H20",
            reason_codes=reasons,
            as_of=as_of,
        )
        mem_ids: list[str] = []
        lessons: list[Any] = []
        if memory is not None:
            lessons = memory.select_memory(
                market=market, sector=str(row.get("sector_code") or ""), ticker=ticker
            )
            mem_ids = [m.memory_id for m in lessons]
        thesis = None
        docs = warehouse.read_documents(market=market, tickers=[ticker], filed_to=as_of)
        source_ids = (
            docs["doc_id"].astype(str).tolist() if not docs.empty and "doc_id" in docs.columns else []
        )
        if router is not None and not llm_capped:
            try:
                rendered = render_prompt(
                    "thesis.jinja",
                    ticker=ticker,
                    company_name=row.get("name_local") or ticker,
                    market=market,
                    sector_name=row.get("sector_name") or "",
                    quant_score=row.get("quant_score"),
                    sector_rank=row.get("sector_rank") or "",
                    sector_count=row.get("sector_count") or "",
                    value_z=row.get("value_z"),
                    momentum_z=row.get("momentum_z"),
                    quality_z=row.get("quality_z"),
                    growth_z=row.get("growth_z"),
                    lowvol_z=row.get("lowvol_z"),
                    revision_z=row.get("revision_z"),
                    horizon="H20",
                    ml_pred=row.get("ml_pred_h20"),
                    ml_pred_lo=row.get("ml_pred_h20_lo"),
                    ml_pred_hi=row.get("ml_pred_h20_hi"),
                    per=row.get("per"),
                    pbr=row.get("pbr"),
                    roic=row.get("roic"),
                    realized_vol=row.get("realized_vol_60d"),
                    reason_codes=reasons,
                    retrieved_chunks=[],
                    hit_rate_prior=prior.hit_rate,
                    n_prior_samples=prior.n_samples,
                    avg_excess_return=prior.avg_excess,
                    agent_memory=lessons,
                )
                resp = router.complete(
                    tier="default",
                    purpose="thesis",
                    messages=[{"role": "user", "content": rendered}],
                    response_schema=ThesisOutput,
                    entity=ticker,
                    job_run_id=run_id,
                    prompt_name="thesis.jinja",
                    prompt_body=rendered,
                )
                thesis = resp.parsed
            except (CostCapExceeded, KillSwitchActive):
                llm_capped = True
                thesis = None
            except Exception:
                thesis = None
        rec = build_recommendation(
            row,
            as_of=as_of,
            market=market,
            n_prior_samples=prior.n_samples,
            hit_rate_prior=prior.hit_rate,
            thesis=thesis,
            memory_ids=mem_ids,
            source_doc_ids=source_ids,
            data_freshness=freshness,
        )
        try:
            warehouse.insert_recommendation(rec)
            recs.append(rec)
            if memory is not None and mem_ids:
                memory.touch_memory(mem_ids)
        except InvariantViolationError:
            return

    tickers = candidates["ticker"].astype(str).tolist() if not candidates.empty else []
    if tickers:
        with_checkpoint(
            state,
            run_id,
            job_name="strategist",
            phase="strategist",
            units=tickers,
            fn=process,
        )

    status = "partial" if llm_capped or not recs else "success"
    if not recs and candidates.empty:
        status = "partial"
    metrics = {
        "n_candidates": int(len(candidates)),
        "n_recs": len(recs),
        "llm_capped": llm_capped,
    }
    finish_run(state, run_id, status=status, metrics=metrics)
    return JobResult(
        job_name="strategist",
        status=status,
        market=market,
        as_of=as_of,
        run_id=run_id,
        steps={"cards": StepResult(status=status)},
        metrics=metrics,
        recs=recs,
    )
