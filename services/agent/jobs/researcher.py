"""Researcher: 開示資料の LLM 要約と qual_score（docs/08-agent-loop.md §5）。

コストキャップ到達時は例外を伝播させず、qual_score=NULL で Strategist へ渡す。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd

from packages.core.interfaces.storage import JobRunRepo, VectorStore, WarehouseRepo
from packages.core.llm.cache import input_hash, prompt_hash
from packages.core.llm.errors import CostCapExceeded, KillSwitchActive
from packages.core.llm.prompts import render_prompt
from packages.core.llm.rag import index_document
from packages.core.llm.router import LLMRouter
from packages.core.llm.schemas import DocSummaryOutput
from packages.core.storage import jp_ticker_aliases
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


def _summary_from_cache(cached: dict[str, Any], row: pd.Series) -> dict[str, Any]:
    return {
        "doc_id": cached.get("doc_id") or row.get("doc_id"),
        "filed_at": row.get("filed_at") or cached.get("filed_at"),
        "doc_type": row.get("doc_type") or cached.get("doc_type"),
        "qualitative_score": cached.get("qualitative_score"),
        "citations": cached.get("citations") or [],
    }


def _summary_payload(
    doc_id: str,
    parsed: DocSummaryOutput,
    p_hash: str,
    i_hash: str,
    *,
    model_id: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    cost_usd: float | None,
    cache_hit: bool,
) -> dict[str, Any]:
    return {
        "doc_id": doc_id,
        "summary_version": 1,
        "model_id": model_id or "unknown",
        "prompt_hash": p_hash,
        "input_hash": i_hash,
        "headline_ja": parsed.summary_ja[:80],
        "summary_ja": parsed.summary_ja,
        "key_points": parsed.key_points,
        "risk_factors": parsed.risk_factors,
        "guidance_tone": parsed.guidance_tone,
        "guidance_evidence": parsed.guidance_evidence,
        "qualitative_score": parsed.qualitative_score,
        "citations": [c.model_dump() for c in parsed.citations],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
        "cache_hit": cache_hit,
    }


def _persist_summary(warehouse: WarehouseRepo, payload: dict[str, Any]) -> None:
    writer = getattr(warehouse, "upsert_document_summaries", None)
    if not callable(writer):
        return
    try:
        writer([payload])
    except Exception:
        return


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
    vector_store: VectorStore | None = None,
    embed: Callable[[str], list[float]] | None = None,
) -> JobResult:
    run_id = begin_run(
        state, job_name="researcher", market=market, trigger=trigger, parent_run_id=parent_run_id
    )
    require_not_failed(state, job_name="analyst", market=market, on_date=as_of, required=False)
    overall = "success"
    metrics: dict[str, Any] = {"llm_capped": False, "n_summaries": 0, "n_chunks": 0}
    embed_fn = embed
    if embed_fn is None and router is not None and callable(getattr(router, "embed", None)):
        embed_fn = router.embed
    embedding_model = "unknown"
    if router is not None:
        try:
            embedding_model = router.config.embeddings.models[router.config.embeddings.primary].litellm_model
        except Exception:
            embedding_model = "unknown"
    qual_rows: list[dict[str, Any]] = []

    docs = warehouse.read_documents(
        market=market, filed_from=as_of - timedelta(days=14), filed_to=as_of
    )
    if tickers:
        if not docs.empty and "ticker" in docs.columns:
            wanted = {alias for t in tickers for alias in jp_ticker_aliases(str(t))}
            docs = docs.loc[docs["ticker"].astype(str).isin(wanted)]
    targets = (
        sorted(docs["ticker"].astype(str).unique().tolist())
        if not docs.empty and "ticker" in docs.columns
        else list(tickers or [])
    )

    def process(ticker: str) -> None:
        nonlocal overall
        aliases = jp_ticker_aliases(ticker)
        subset = (
            docs.loc[docs["ticker"].astype(str).isin(aliases)]
            if not docs.empty and "ticker" in docs.columns
            else pd.DataFrame()
        )
        summaries: list[dict[str, Any]] = []
        for _, row in subset.iterrows():
            doc_id = str(row.get("doc_id") or "")
            rendered = render_prompt(
                "doc_summary.jinja",
                company_name=row.get("title") or ticker,
                ticker=ticker,
                filed_at=row.get("filed_at"),
                doc_type_ja=row.get("doc_type") or "",
                prev_doc_available=False,
                schema_json=DocSummaryOutput.model_json_schema(),
            )
            p_hash = prompt_hash("doc_summary.jinja", rendered)
            i_hash = input_hash({"doc_id": doc_id, "messages": rendered})
            cached = None
            finder = getattr(warehouse, "find_summary", None)
            if callable(finder):
                try:
                    cached = finder(doc_id=doc_id, prompt_hash=p_hash, input_hash=i_hash)
                except TypeError:
                    cached = finder(doc_id=doc_id)
            if cached:
                summaries.append(_summary_from_cache(cached, row))
                metrics["n_summaries"] += 1
                continue
            if router is None:
                continue
            try:
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
                payload = _summary_payload(
                    doc_id,
                    parsed,
                    p_hash,
                    i_hash,
                    model_id=getattr(resp, "model_id", None),
                    input_tokens=getattr(resp, "input_tokens", None),
                    output_tokens=getattr(resp, "output_tokens", None),
                    cost_usd=getattr(resp, "cost_usd", None),
                    cache_hit=getattr(resp, "was_cache_hit", False),
                )
                _persist_summary(warehouse, payload)
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
        if vector_store is not None and embed_fn is not None:
            for _, row in subset.iterrows():
                indexed = _index_row(
                    warehouse,
                    row,
                    market=market,
                    vector_store=vector_store,
                    embed=embed_fn,
                    embedding_model=embedding_model,
                )
                metrics["n_chunks"] += indexed
        agg = aggregate_qual_score(summaries, as_of)
        qual_rows.append({"ticker": ticker, **agg})

    if targets:
        with_checkpoint(
            state,
            run_id,
            job_name="researcher",
            phase="researcher",
            units=targets,
            fn=process,
        )
    if router is None:
        # キャッシュがあれば使う。新規要約はスキップして定量のみで後続へ。
        metrics["llm_skipped"] = True
        overall = "partial"

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


def _index_row(
    warehouse: WarehouseRepo,
    row: pd.Series,
    *,
    market: str,
    vector_store: VectorStore,
    embed: Callable[[str], list[float]],
    embedding_model: str,
) -> int:
    doc_id = str(row.get("doc_id") or "")
    if not doc_id:
        return 0
    getter = getattr(warehouse, "get_document_text", None)
    text = ""
    if callable(getter):
        try:
            text = str(getter(doc_id) or "")
        except Exception:
            text = ""
    if len(text.strip()) < 20:
        return 0
    filed = row.get("filed_at")
    filed_at = filed if isinstance(filed, datetime) else None
    if filed_at is None and hasattr(filed, "date"):
        try:
            filed_at = datetime.combine(filed.date(), datetime.min.time())
        except Exception:
            filed_at = None
    try:
        return index_document(
            doc_id=doc_id,
            text=text,
            market=str(row.get("market") or market),
            ticker=str(row.get("ticker") or "") or None,
            doc_type=str(row.get("doc_type") or "") or None,
            filed_at=filed_at,
            embed=embed,
            vector_store=vector_store,
            embedding_model=embedding_model,
        )
    except Exception:
        return 0
