"""Strategist: 推奨カード生成（docs/08-agent-loop.md §6）。

LLM が止まっても定量スコアだけでカードを出す。不完全な推奨は破棄する。
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd

from packages.core.factors.scoring import total_score
from packages.core.factors.screening import (
    MIN_PRIOR_SAMPLES,
    UniverseFilter,
    assign_reason_codes,
    compute_hit_rate_prior,
    conviction_from_score,
    determine_action,
    select_recommendation_candidates,
)
from packages.core.interfaces.storage import JobRunRepo, MemoryRepo, SearchHit, VectorStore, WarehouseRepo
from packages.core.llm.errors import (
    CostCapExceeded,
    InvariantViolationError,
    KillSwitchActive,
)
from packages.core.llm.prompts import render_prompt
from packages.core.llm.router import LLMRouter
from packages.core.llm.schemas import Citation, ThesisOutput
from packages.core.storage import InvariantViolation, StorageError
from services.agent.checkpoint import with_checkpoint
from services.agent.deps import attach_step_failures, begin_run, finish_run, first_step_error
from services.agent.types import JobResult, StepResult

logger = logging.getLogger(__name__)

FALLBACK_BEAR = (
    "定量スコア上位だが、開示資料の定性分析が停止または不足しているため、"
    "バリュートラップと業績モメンタム剥落の両方を却下理由として残す。"
    "信頼区間が広く、母数不足なら確信度は低に固定する。"
)
FILL_BEAR = (
    "定量スコアの順位補充であり、ML予測と定量スコアの一致は確認していない。"
    "バリュートラップと業績モメンタム剥落の両方を却下理由として残す。"
    "確信度は低に固定し、コア候補より優先して採用しない。"
)
# ML 未学習時に使う、情報のない広い区間（ホライズン20営業日）。
FALLBACK_CI_HALF_WIDTH = 0.20


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in {float("inf"), float("-inf")}:
        return None
    return number


def _interval_from_row(row: pd.Series) -> tuple[float | None, float, float]:
    """ML 区間が無ければ実現ボラ、それも無ければ広いデフォルトで埋める。

    区間なしの推奨は不変条件で挿入できない。パイプラインを落とす代わりに
    「情報がない」ことを幅で表現する。
    """
    pred = _finite(row.get("ml_pred_h20"))
    lo = _finite(row.get("ml_pred_h20_lo"))
    hi = _finite(row.get("ml_pred_h20_hi"))
    if lo is not None and hi is not None and hi > lo:
        return pred, lo, hi
    vol = _finite(row.get("realized_vol_60d"))
    center = pred if pred is not None else 0.0
    if vol is not None and vol > 0:
        half = float(vol) * (20.0 / 252.0) ** 0.5
        return pred, center - half, center + half
    return pred, center - FALLBACK_CI_HALF_WIDTH, center + FALLBACK_CI_HALF_WIDTH


def _high_vol_regime(warehouse: WarehouseRepo, *, market: str, as_of: date) -> bool:
    """ベンチマーク水準から高ボラレジームかを判定する。失敗しても推奨は出す。"""
    from packages.core.models.regime import vol_regime_from_levels

    series_id = "NIKKEI225" if market == "JP" else "SP500"
    getter = getattr(warehouse, "get_macro_as_of", None)
    if not callable(getter):
        return False
    try:
        rows = getter(series_id, as_of=as_of, limit=1300) or []
    except Exception:
        return False
    if not rows:
        return False
    frame = pd.DataFrame(rows)
    date_col = next(
        (c for c in ("observation_date", "date", "trade_date") if c in frame.columns),
        None,
    )
    if date_col is None or "value" not in frame.columns:
        return False
    levels = pd.Series(
        pd.to_numeric(frame["value"], errors="coerce").to_numpy(),
        index=pd.to_datetime(frame[date_col], errors="coerce"),
    ).dropna().sort_index()
    return vol_regime_from_levels(levels).high_vol


def _force_conviction(raw: str, n_prior: int) -> str:
    if n_prior < MIN_PRIOR_SAMPLES:
        return "low"
    return raw


def _conviction_score(row: pd.Series) -> float:
    """quant_score（0-100）を 0.0..1.0 に写す。欠損・非有限は 0.5。"""
    raw = _finite(row.get("quant_score"))
    if raw is None:
        return 0.5
    score = raw / 100.0
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score


def _chunks_from_docs(
    warehouse: WarehouseRepo, docs: pd.DataFrame, *, k: int = 8
) -> list[SearchHit]:
    hits: list[SearchHit] = []
    if docs is None or getattr(docs, "empty", True):
        return hits
    for _, row in docs.head(k * 2).iterrows():
        doc_id = str(row.get("doc_id") or "")
        if not doc_id:
            continue
        getter = getattr(warehouse, "get_document_text", None)
        text = str(getter(doc_id) if callable(getter) else "") or str(row.get("title") or "")
        snippet = text.strip()[:1200]
        if len(snippet) < 20:
            continue
        filed = row.get("filed_at")
        hits.append(
            SearchHit(
                chunk_id=f"{doc_id}:excerpt",
                doc_id=doc_id,
                text=snippet,
                score=0.1,
                ticker=str(row.get("ticker") or ""),
                market=str(row.get("market") or ""),
                doc_type=str(row.get("doc_type") or ""),
                filed_at=filed if hasattr(filed, "date") else None,
                title=str(row.get("title") or ""),
            )
        )
        if len(hits) >= k:
            break
    return hits


def _retrieve_chunks(
    warehouse: WarehouseRepo,
    *,
    ticker: str,
    market: str,
    as_of: date,
    reasons: list[str],
    docs: pd.DataFrame,
    vector_store: VectorStore | None = None,
    embed: Callable[[str], list[float]] | None = None,
) -> list[SearchHit]:
    """ハイブリッド RAG。両方空なら直近開示の本文抜粋に落とす。"""
    from packages.core.llm.rag import retrieve

    query = " ".join(str(c) for c in reasons) + " リスク 懸念 不確実性"
    keyword = warehouse if callable(getattr(warehouse, "search_text", None)) else None
    hits: list[SearchHit] = []
    try:
        hits = retrieve(
            query,
            ticker=ticker,
            market=market,
            k=8,
            as_of=as_of,
            keyword_search=keyword,
            vector_store=vector_store,
            embed=embed,
        )
    except Exception:
        hits = []
    if hits:
        return hits
    return _chunks_from_docs(warehouse, docs)


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
    if not (rec.get("thesis_ja") or "").strip():
        raise InvariantViolationError("thesis_ja が空です")
    score = _finite(rec.get("conviction_score"))
    if score is None or score < 0.0 or score > 1.0:
        raise InvariantViolationError("conviction_score がありません")
    rec["conviction_score"] = score
    if not rec.get("reason_codes"):
        raise InvariantViolationError("reason_codes が空です")


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
    high_vol_regime: bool = False,
    candidate_tier: str = "core",
) -> dict[str, Any]:
    action = determine_action(row, is_held=False) or "watch"
    conv_score = _conviction_score(row)
    is_fill = candidate_tier == "fill"
    if thesis is not None:
        raw_conv = thesis.conviction
        thesis_ja = thesis.thesis_ja
        bear = thesis.bear_case_ja
        inval = thesis.invalidation_ja
        citations = [c.model_dump() for c in thesis.citations]
    else:
        raw_conv = "low"
        if is_fill:
            thesis_ja = (
                f"{row.get('ticker')} は定量スコア {row.get('quant_score')} で"
                "1日の件数目標を埋める補充候補。"
                f"ML予測 {row.get('ml_pred_h20')} "
                f"[{row.get('ml_pred_h20_lo')}, {row.get('ml_pred_h20_hi')}]。"
                "定量とMLの一致は確認していない。"
            )
            bear = FILL_BEAR
        else:
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
        high_vol_regime=high_vol_regime,
    )
    if thesis is not None:
        # LLM の conviction と規則側の厳しい方を取る。
        order = {"low": 0, "medium": 1, "high": 2}
        level = raw_conv if order[raw_conv] <= order[level] else level
    level = _force_conviction(level, n_prior_samples)
    if is_fill:
        level = "low"
    expected_ret, expected_lo, expected_hi = _interval_from_row(row)
    ml_pred = _finite(row.get("ml_pred_h20"))
    reasons = [str(c) for c in (row.get("reason_codes") or []) if str(c).strip()]
    if is_fill and "RANK_FILL" not in reasons:
        reasons.append("RANK_FILL")
    if not reasons:
        reasons = ["MODEL_LOW_CONFIDENCE"]
    rec = {
        "rec_id": str(uuid.uuid4()),
        "as_of": as_of,
        "market": market,
        "ticker": str(row.get("ticker")),
        "action": action,
        "horizon": "H20",
        "quant_score": _finite(row.get("quant_score")),
        "qual_score": _finite(row.get("qual_score")),
        "total_score": _finite(row.get("total_score")),
        "ml_pred": ml_pred,
        "ml_pred_h20": ml_pred,
        "expected_ret": expected_ret,
        "expected_ret_lo": expected_lo,
        "expected_ret_hi": expected_hi,
        "thesis_ja": thesis_ja,
        "bear_case_ja": bear,
        "invalidation_ja": inval,
        "conviction": level,
        "conviction_score": conv_score,
        "n_prior_samples": n_prior_samples,
        "hit_rate_prior": hit_rate_prior,
        "reason_codes": reasons,
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
    vector_store: VectorStore | None = None,
    embed: Callable[[str], list[float]] | None = None,
) -> JobResult:
    run_id = begin_run(
        state, job_name="strategist", market=market, trigger=trigger, parent_run_id=parent_run_id
    )
    try:
        return _strategist_body(
            run_id,
            market,
            as_of,
            state=state,
            warehouse=warehouse,
            memory=memory,
            router=router,
            scores=scores,
            outcomes=outcomes,
            universe_filter=universe_filter,
            max_per_day=max_per_day,
            researcher_qual=researcher_qual,
            vector_store=vector_store,
            embed=embed,
        )
    except Exception as exc:
        finish_run(state, run_id, status="failed", error=exc)
        raise


def _strategist_body(
    run_id: int,
    market: str,
    as_of: date,
    *,
    state: JobRunRepo,
    warehouse: WarehouseRepo,
    memory: MemoryRepo | None,
    router: LLMRouter | None,
    scores: pd.DataFrame | None,
    outcomes: pd.DataFrame | None,
    universe_filter: UniverseFilter | None,
    max_per_day: int,
    researcher_qual: list[dict[str, Any]] | None,
    vector_store: VectorStore | None = None,
    embed: Callable[[str], list[float]] | None = None,
) -> JobResult:
    if scores is None:
        scores = warehouse.read_scores_daily(as_of=as_of, market=market)
    if scores is None or scores.empty:
        err = RuntimeError(
            "scores が空です。先に分析ジョブを成功させてください。"
        )
        finish_run(
            state,
            run_id,
            status="failed",
            metrics={"reason": "no_scores", "failed_steps": ["scores"]},
            error=err,
        )
        return JobResult(
            job_name="strategist",
            status="failed",
            market=market,
            as_of=as_of,
            run_id=run_id,
            error=str(err),
            steps={"scores": StepResult(status="failed", error=str(err))},
            metrics={"reason": "no_scores"},
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
    candidates = select_recommendation_candidates(work, max_per_day=max_per_day)

    freshness = []
    try:
        fresh = warehouse.read_data_freshness()
        if fresh is not None and not fresh.empty:
            freshness = fresh.to_dict(orient="records")
    except Exception:
        freshness = []

    recs: list[dict[str, Any]] = []
    llm_capped = False
    discarded = 0
    high_vol_regime = _high_vol_regime(warehouse, market=market, as_of=as_of)

    def process(ticker: str) -> None:
        nonlocal llm_capped, discarded
        row = candidates.loc[candidates["ticker"].astype(str) == ticker].iloc[0]
        reasons = assign_reason_codes(row)
        if str(row.get("candidate_tier") or "core") == "fill" and "RANK_FILL" not in reasons:
            reasons.append("RANK_FILL")
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
                    retrieved_chunks=_retrieve_chunks(
                        warehouse,
                        ticker=ticker,
                        market=market,
                        as_of=as_of,
                        reasons=reasons,
                        docs=docs,
                        vector_store=vector_store,
                        embed=embed if embed is not None else getattr(router, "embed", None),
                    ),
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
        try:
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
                high_vol_regime=high_vol_regime,
                candidate_tier=str(row.get("candidate_tier") or "core"),
            )
            warehouse.insert_recommendation(rec)
            recs.append(rec)
            if memory is not None and mem_ids:
                memory.touch_memory(mem_ids)
        except (InvariantViolationError, InvariantViolation, StorageError) as exc:
            logger.warning("strategist: discard ticker=%s: %s", ticker, exc)
            discarded += 1
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

    status = "partial" if llm_capped or not recs or discarded else "success"
    if not recs and candidates.empty:
        status = "partial"
    steps = {"cards": StepResult(status=status)}
    if status != "success" and not recs:
        steps["cards"] = StepResult(
            status="failed" if status == "failed" else "partial",
            error="推奨カードを1件も生成できませんでした",
        )
    metrics = attach_step_failures(
        {
            "n_candidates": len(candidates),
            "n_core_candidates": int(
                (candidates["candidate_tier"] == "core").sum()
            )
            if not candidates.empty and "candidate_tier" in candidates.columns
            else 0,
            "n_fill_candidates": int(
                (candidates["candidate_tier"] == "fill").sum()
            )
            if not candidates.empty and "candidate_tier" in candidates.columns
            else 0,
            "n_recs": len(recs),
            "n_discarded": discarded,
            "llm_capped": llm_capped,
        },
        steps,
    )
    job_error = first_step_error(steps) if status in {"failed", "partial"} else None
    finish_run(
        state,
        run_id,
        status=status,
        metrics=metrics,
        error=RuntimeError(job_error) if job_error else None,
    )
    return JobResult(
        job_name="strategist",
        status=status,
        market=market,
        as_of=as_of,
        run_id=run_id,
        steps=steps,
        metrics=metrics,
        recs=recs,
        error=job_error,
    )
