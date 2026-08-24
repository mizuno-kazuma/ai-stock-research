"""Researcher: 開示資料の LLM 要約と qual_score（docs/08-agent-loop.md §5）。

コストキャップ到達時は例外を伝播させず、qual_score=NULL で Strategist へ渡す。
"""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from packages.core.interfaces.storage import JobRunRepo, MemoryRecord, WarehouseRepo
from packages.core.llm.errors import CostCapExceeded, KillSwitchActive
from packages.core.llm.prompts import render_prompt
from packages.core.llm.router import LLMRouter
from packages.core.llm.schemas import DocSummaryOutput
from services.agent.checkpoint import with_checkpoint
from services.agent.deps import begin_run, finish_run, require_not_failed
from services.agent.types import JobResult, StepResult

TYPE_WEIGHTS = {
    "earnings_flash": 1.0,
    "guidance_revision": 1.2,
    "quarterly_report": 0.9,
    "annual_report": 0.8,
    "other_disclosure": 0.3,
}


def aggregate_qual_score(summaries: list[dict[str, Any]], as_of: date) -> dict[str, Any]:
    """資料の鮮度で重み付けした加重平均。confidence はスコアの大きさから独立。"""
    if not summaries:
        return {"score": None, "confidence": None, "doc_count": 0}
    weights, scores = [], []
    ages = []
    for s in summaries:
        filed = s.get("filed_at")
        if hasattr(filed, "date"):
            filed_d = filed.date()
        else:
            filed_d = filed or as_of
        age_days = max((as_of - filed_d).days, 0)
        ages.append(age_days)
        recency_w = 0.5 ** (age_days / 90.0)
        type_w = TYPE_WEIGHTS.get(str(s.get("doc_type") or "other_disclosure"), 0.3)
        n_cit = len(s.get("citations") or [])
        evidence_w = min(n_cit / 3.0, 1.5)
        weights.append(recency_w * type_w * evidence_w)
        scores.append(float(s.get("qualitative_score") or 0.0))
    w = np.array(weights, dtype=float)
    sc = np.array(scores, dtype=float)
    if w.sum() == 0:
        score = float(np.mean(sc))
    else:
        score = float(np.average(sc, weights=w))
    min_age = min(ages) if ages else 365
    dispersion = float(np.std(sc)) if len(sc) > 1 else 0.0
    score_dispersion = min(dispersion / 2.0, 1.0)
    confidence = min(
        0.3 * min(len(summaries) / 3.0, 1.0)
        + 0.4 * (0.5 ** (min_age / 60.0))
        + 0.3 * (1.0 - score_dispersion),
        1.0,
    )
    return {
        "score": float(np.clip(score, -1.0, 1.0)),
        "confidence": float(confidence),
        "doc_count": len(summaries),
    }


def researcher(
    market: str,
    as_of: date,
    *,
    state: JobRunRepo,
    warehouse: WarehouseRepo,
    router: LLMRouter | None = None,
    tickers: list[str] | None = None,
    trigger: str = "schedule",
    parent_run_id: int | None = None,
) -> JobResult:
    run_id = begin_run(
        state, job_name="researcher", market=market, trigger=trigger, parent_run_id=parent_run_id
    )
    require_not_failed(state, job_name="analyst", market=market, on_date=as_of, required=False)
    overall = "success"
    metrics: dict[str, Any] = {"llm_capped": False, "n_summaries": 0}
    qual_rows: list[dict[str, Any]] = []

    docs = warehouse.read_documents(market=market, filed_to=as_of)
    if tickers:
        if not docs.empty and "ticker" in docs.columns:
            docs = docs.loc[docs["ticker"].astype(str).isin(tickers)]
    targets = (
        sorted(docs["ticker"].astype(str).unique().tolist())
        if not docs.empty and "ticker" in docs.columns
        else list(tickers or [])
    )

    def process(ticker: str) -> None:
        nonlocal overall
        subset = (
            docs.loc[docs["ticker"].astype(str) == ticker]
            if not docs.empty and "ticker" in docs.columns
            else pd.DataFrame()
        )
        summaries: list[dict[str, Any]] = []
        for _, row in subset.iterrows():
            doc_id = str(row.get("doc_id") or "")
            if router is None:
                break
            try:
                rendered = render_prompt(
                    "doc_summary.jinja",
                    company_name=row.get("title") or ticker,
                    ticker=ticker,
                    filed_at=row.get("filed_at"),
                    doc_type_ja=row.get("doc_type") or "",
                    prev_doc_available=False,
                    schema_json=DocSummaryOutput.model_json_schema(),
                )
                resp = router.complete(
                    tier="bulk",
                    purpose="doc_summary",
                    messages=[{"role": "user", "content": rendered}],
                    response_schema=DocSummaryOutput,
                    entity=doc_id,
                    job_run_id=run_id,
                    prompt_name="doc_summary.jinja",
                    prompt_body=rendered,
                )
                parsed = resp.parsed
                if parsed is None:
                    continue
                summaries.append(
                    {
                        "doc_id": doc_id,
                        "filed_at": row.get("filed_at"),
                        "doc_type": row.get("doc_type"),
                        "qualitative_score": parsed.qualitative_score,
                        "citations": [c.model_dump() for c in parsed.citations],
                    }
                )
                metrics["n_summaries"] += 1
            except (CostCapExceeded, KillSwitchActive):
                overall = "partial"
                metrics["llm_capped"] = True
                return
            except Exception:
                overall = "partial"
                continue
        agg = aggregate_qual_score(summaries, as_of)
        qual_rows.append({"ticker": ticker, **agg})

    if targets and router is not None:
        with_checkpoint(
            state,
            run_id,
            job_name="researcher",
            phase="researcher",
            units=targets,
            fn=process,
        )
    else:
        # LLM なし / 対象なし → 定量のみで後続へ。
        if router is None:
            metrics["llm_capped"] = False
            overall = "partial"
        for t in targets:
            qual_rows.append({"ticker": t, "score": None, "confidence": None, "doc_count": 0})

    metrics["n_tickers"] = len(targets)
    finish_run(state, run_id, status=overall, metrics=metrics)
    return JobResult(
        job_name="researcher",
        status=overall,
        market=market,
        as_of=as_of,
        run_id=run_id,
        steps={"summaries": StepResult(status=overall)},
        metrics=metrics,
        recs=qual_rows,
    )
