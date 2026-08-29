"""Critic: 機械的検証のあと LLM で敵対的レビュー（docs/08-agent-loop.md §7）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from packages.core.factors.screening import MIN_PRIOR_SAMPLES
from packages.core.interfaces.storage import JobRunRepo, WarehouseRepo
from packages.core.llm.citations import CitationVerdict, verify_citation
from packages.core.llm.errors import CostCapExceeded, KillSwitchActive
from packages.core.llm.prompts import render_prompt
from packages.core.llm.router import LLMRouter
from packages.core.llm.schemas import Citation, CriticOutput
from services.agent.checkpoint import with_checkpoint
from services.agent.deps import begin_run, finish_run
from services.agent.types import JobResult, StepResult

BOILERPLATE_PATTERNS = [
    "市場環境の悪化",
    "予想外の事態",
    "リスクは限定的",
    "特にありません",
    "一般的なリスク",
    "マクロ環境の変化",
    "地政学リスク",
]


@dataclass
class Issue:
    severity: str
    code: str
    detail: str = ""


def mechanical_checks(
    rec: dict[str, Any],
    *,
    warehouse: WarehouseRepo | None = None,
    jquants_plan: str = "light",
    expected_freshness: dict[str, date] | None = None,
) -> list[Issue]:
    issues: list[Issue] = []

    for raw in rec.get("citations") or []:
        cit = raw if isinstance(raw, Citation) else Citation.model_validate(raw)
        # 定量カードの合成引用（quant:）は開示資料ではないので本文検証をしない。
        if str(cit.doc_id).startswith("quant:"):
            continue
        if warehouse is None:
            continue
        verdict = verify_citation(
            cit,
            get_document=warehouse.get_document,
            get_document_text=warehouse.get_document_text,
        )
        if verdict in (CitationVerdict.DOC_NOT_FOUND, CitationVerdict.QUOTE_NOT_FOUND):
            issues.append(Issue("critical", "citation_not_found", detail=str(cit)))

    for f in rec.get("data_freshness") or []:
        source = f.get("source")
        latest = f.get("latest_as_of")
        if expected_freshness and source in expected_freshness and latest is not None:
            expected = expected_freshness[source]
            lag = (expected - latest).days if hasattr(expected, "toordinal") else 0
            if lag > 3:
                issues.append(Issue("major", "stale_data", detail=f"{source}: {latest}"))

    if rec.get("entry_ref_source") == "jquants" and jquants_plan == "free":
        issues.append(Issue("critical", "delayed_price_as_current"))

    bear = rec.get("bear_case_ja") or ""
    if len(bear) < 20:
        issues.append(Issue("critical", "empty_bear_case"))
    elif any(p in bear for p in BOILERPLATE_PATTERNS) and not any(
        ch.isdigit() for ch in bear
    ):
        issues.append(Issue("major", "boilerplate_bear_case"))

    if rec.get("conviction") != "low" and (rec.get("n_prior_samples") or 0) < MIN_PRIOR_SAMPLES:
        issues.append(Issue("major", "conviction_without_evidence"))

    lo = rec.get("expected_ret_lo")
    hi = rec.get("expected_ret_hi")
    if lo is None or hi is None:
        issues.append(Issue("critical", "missing_confidence_interval"))
    elif float(hi) - float(lo) < 0.01:
        issues.append(Issue("major", "suspiciously_narrow_ci"))

    as_of = rec.get("as_of")
    if warehouse is not None and as_of is not None:
        for doc_id in rec.get("source_doc_ids") or []:
            if str(doc_id).startswith("quant:"):
                continue
            doc = warehouse.get_document(str(doc_id))
            if doc and doc.get("filed_at") is not None:
                filed = doc["filed_at"]
                filed_d = filed.date() if hasattr(filed, "date") else filed
                if filed_d > as_of:
                    issues.append(Issue("critical", "future_document_cited", detail=str(doc_id)))

    thesis = rec.get("thesis_ja") or ""
    if any(w in thesis for w in ["必ず", "確実に", "間違いなく"]):
        issues.append(Issue("major", "overconfident_language"))

    return issues


REVISED_FIELDS = {"thesis_ja", "bear_case_ja", "invalidation_ja", "conviction"}


def _apply_revised_fields(rec: dict[str, Any], revised: dict[str, str] | None) -> bool:
    """Critic の修正案をカード本文に書き戻す（docs/08 §7.4）。"""
    if not revised:
        return False
    applied = False
    for key, value in revised.items():
        if key not in REVISED_FIELDS:
            continue
        text = str(value or "").strip()
        if not text:
            continue
        if key == "conviction":
            if text not in {"low", "medium", "high"}:
                continue
            if (rec.get("n_prior_samples") or 0) < MIN_PRIOR_SAMPLES:
                text = "low"
        rec[key] = text
        applied = True
    return applied


def _verdict_from_issues(issues: list[Issue]) -> str:
    n_crit = sum(1 for i in issues if i.severity == "critical")
    n_major = sum(1 for i in issues if i.severity == "major")
    if n_crit or n_major >= 2:
        return "rejected"
    if n_major == 1:
        return "revised"
    return "approved"


def critic(
    market: str,
    as_of: date,
    *,
    state: JobRunRepo,
    warehouse: WarehouseRepo,
    router: LLMRouter | None = None,
    recs: list[dict[str, Any]] | None = None,
    jquants_plan: str = "light",
    trigger: str = "schedule",
    parent_run_id: int | None = None,
) -> JobResult:
    run_id = begin_run(
        state, job_name="critic", market=market, trigger=trigger, parent_run_id=parent_run_id
    )
    pending = recs
    if pending is None:
        pending = warehouse.get_recommendations(as_of=as_of, market=market, critic_verdict=None)
    pending = list(pending or [])
    counts = {"approved": 0, "revised": 0, "rejected": 0}
    llm_capped = False

    def process(rec_id: str) -> None:
        nonlocal llm_capped
        rec = next(r for r in pending if str(r.get("rec_id")) == rec_id)
        issues = mechanical_checks(rec, warehouse=warehouse, jquants_plan=jquants_plan)
        verdict = _verdict_from_issues(issues)
        notes = ""
        if verdict != "rejected" and router is not None and not llm_capped:
            try:
                rendered = render_prompt(
                    "critic.jinja",
                    recommendation_json=rec,
                    data_freshness=rec.get("data_freshness") or [],
                    feature_version=rec.get("feature_version") or "",
                    source_docs=[{"doc_id": d, "filed_at": ""} for d in rec.get("source_doc_ids") or []],
                    citation_verdicts=[],
                )
                resp = router.complete(
                    tier="default",
                    purpose="critic",
                    messages=[{"role": "user", "content": rendered}],
                    response_schema=CriticOutput,
                    entity=rec_id,
                    job_run_id=run_id,
                    prompt_name="critic.jinja",
                    prompt_body=rendered,
                )
                if resp.parsed is not None:
                    verdict = resp.parsed.verdict
                    notes = resp.parsed.notes_ja
                    applied = _apply_revised_fields(rec, resp.parsed.revised_fields)
                    if applied:
                        notes = notes or "Critic の修正案を本文に反映しました。"
            except (CostCapExceeded, KillSwitchActive):
                llm_capped = True
            except Exception:
                pass
        if len((rec.get("bear_case_ja") or "").strip()) < 20:
            verdict = "rejected"
        rec["critic_verdict"] = verdict
        rec["critic_notes_ja"] = notes
        rec["critic_issues"] = [i.__dict__ for i in issues]
        payload = {
            "critic_verdict": verdict,
            "critic_notes_ja": notes,
            "thesis_ja": rec.get("thesis_ja"),
            "bear_case_ja": rec.get("bear_case_ja"),
            "invalidation_ja": rec.get("invalidation_ja"),
            "conviction": rec.get("conviction"),
        }
        warehouse.update_recommendation(rec_id, payload)
        counts[verdict] = counts.get(verdict, 0) + 1

    units = [str(r.get("rec_id")) for r in pending]
    if units:
        with_checkpoint(
            state,
            run_id,
            job_name="critic",
            phase="critic",
            units=units,
            fn=process,
        )

    n = max(sum(counts.values()), 1)
    reject_rate = counts["rejected"] / n
    status = "partial" if llm_capped else "success"
    if not pending:
        status = "partial"
    metrics = {**counts, "reject_rate": reject_rate, "llm_capped": llm_capped, "n": len(pending)}
    finish_run(state, run_id, status=status, metrics=metrics)
    return JobResult(
        job_name="critic",
        status=status,
        market=market,
        as_of=as_of,
        run_id=run_id,
        steps={"review": StepResult(status=status)},
        metrics=metrics,
        recs=pending,
    )
