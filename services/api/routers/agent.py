"""エージェント（docs/09-api-spec.md §2.8）。"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sse_starlette.sse import EventSourceResponse

from packages.core.storage import to_dict
from packages.schemas.agent import (
    AgentCost,
    AgentMemoryList,
    AgentMemoryPatch,
    CostByPurpose,
    CostByTier,
    CostDailyPoint,
    CriticReason,
    CriticStats,
    JobRunList,
    LLMCall,
)
from packages.schemas.agent import AgentMemory as MemorySchema
from packages.schemas.agent import JobRun as JobRunSchema
from packages.schemas.common import Envelope, OkResponse
from services.api.deps import AppState, User, get_app_state, require_user
from services.api.envelope import wrap
from services.api.errors import not_found, validation_error
from services.api.events import sse_iterator
from services.api.mapping import job_from_row, memory_from_row
from services.api.runtime import kick_agent_job
from services.api.util import as_list, resolve_market, utc_now

router = APIRouter(tags=["agent"])

KNOWN_JOBS = {
    "collector",
    "collector_jp",
    "collector_us",
    "analyst",
    "researcher",
    "strategist",
    "critic",
    "evaluator",
    "weekly_review",
    "model_retrain",
    "garch_refit",
    "backtest",
}


def _seed_job(job_run_id: int, payload: dict) -> dict | None:
    for item in payload.get("jobs") or []:
        if int(item.get("job_run_id") or 0) == job_run_id:
            return item
    return None


@router.get("/agent/jobs", response_model=Envelope[JobRunList])
def list_jobs(
    limit: int = Query(default=50, ge=1, le=200),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[JobRunList]:
    rows = state.sqlite.get_job_runs(limit=limit)
    items = []
    for row in rows:
        extra = _seed_job(int(row.id), state.payload)
        items.append(job_from_row(row, seed=extra))
    if not items:
        items = [job_from_row(j, seed=j) for j in state.payload.get("jobs") or []][:limit]
    return wrap(state, JobRunList(items=items, total=len(items)))


@router.get("/agent/jobs/{job_run_id}", response_model=Envelope[JobRunSchema])
def get_job(
    job_run_id: int,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[JobRunSchema]:
    row = state.sqlite.get_job_run(job_run_id)
    if row:
        return wrap(state, job_from_row(row, seed=_seed_job(job_run_id, state.payload)))
    extra = _seed_job(job_run_id, state.payload)
    if extra:
        return wrap(state, job_from_row(extra, seed=extra))
    raise not_found(f"ジョブ実行 {job_run_id} は存在しません。")


@router.post("/agent/jobs/{job_name}/run", response_model=Envelope[JobRunSchema])
def run_job(
    job_name: str,
    background: BackgroundTasks,
    market: str | None = Query(default=None),
    as_of: dt.date | None = Query(default=None),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[JobRunSchema]:
    if job_name not in KNOWN_JOBS:
        raise validation_error(f"未知のジョブ名です: {job_name}")
    if market:
        market = resolve_market(market)
    run_id = state.sqlite.start_job_run(job_name, trigger="manual", market=market)
    state.bus.publish_nowait(
        "job_progress",
        {
            "job_run_id": run_id,
            "job_name": job_name,
            "phase": "queued",
            "completed": 0,
            "total": 1,
            "eta_sec": 1,
        },
    )

    background.add_task(
        kick_agent_job,
        state,
        job_name=job_name,
        run_id=run_id,
        market=market,
        as_of=as_of,
    )
    row = state.sqlite.get_job_run(run_id)
    assert row is not None
    return wrap(state, job_from_row(row))


@router.post("/agent/jobs/{job_run_id}/cancel", response_model=Envelope[OkResponse])
def cancel_job(
    job_run_id: int,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[OkResponse]:
    row = state.sqlite.get_job_run(job_run_id)
    if row is None:
        raise not_found(f"ジョブ実行 {job_run_id} は存在しません。")
    if row.status not in {"running"}:
        raise validation_error(f"実行中ではないジョブはキャンセルできません（status={row.status}）。")
    state.sqlite.update_job_run(job_run_id, status="cancelled", finished=True)
    state.bus.publish_nowait(
        "job_finished",
        {"job_run_id": job_run_id, "status": "cancelled", "duration_sec": row.duration_sec, "failed_steps": []},
    )
    return wrap(state, OkResponse(ok=True, id=job_run_id, message_ja="ジョブをキャンセルしました。"))


def _prune_seed_jobs(state: AppState) -> None:
    """SQLite から消した実行がシードに残って再表示されないようにする。"""
    remaining = {int(row.id) for row in state.sqlite.get_job_runs(limit=200)}
    jobs = state.payload.get("jobs")
    if jobs is None:
        return
    state.payload["jobs"] = [j for j in jobs if int(j.get("job_run_id") or 0) in remaining]


@router.delete("/agent/jobs", response_model=Envelope[OkResponse])
def clear_jobs(
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[OkResponse]:
    deleted = state.sqlite.clear_finished_job_runs()
    _prune_seed_jobs(state)
    remaining = len(state.sqlite.get_job_runs(limit=200))
    if remaining:
        message = f"完了した実行履歴を{deleted}件削除しました。実行中のジョブは残しています。"
    elif deleted:
        message = f"実行履歴を{deleted}件削除しました。"
    else:
        message = "削除する実行履歴はありませんでした。"
    return wrap(state, OkResponse(ok=True, message_ja=message))


@router.get("/agent/memory", response_model=Envelope[AgentMemoryList])
def list_memory(
    scope: str | None = None,
    scope_value: str | None = None,
    is_active: bool | None = Query(default=True),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[AgentMemoryList]:
    rows = state.sqlite.get_agent_memories(
        scope=scope,
        scope_value=scope_value,
        active_only=bool(is_active) if is_active is not None else False,
    )
    seed_by_id = {str(m.get("memory_id")): m for m in state.payload.get("agent_memory") or []}
    items = [memory_from_row(r, seed=seed_by_id.get(str(r.memory_id))) for r in rows]
    if not items:
        items = [
            memory_from_row(
                {
                    **m,
                    "memory_id": str(m.get("memory_id")),
                    "n_observations": m.get("n_evidence") or 0,
                    "confidence": 0.4 if m.get("harmful_flag") else 0.75,
                    "derived_from": [],
                    "lesson_ja": m.get("lesson_ja"),
                    "evidence_ja": m.get("evidence_ja"),
                    "created_at": m.get("updated_at"),
                },
                seed=m,
            )
            for m in state.payload.get("agent_memory") or []
            if (scope is None or m.get("scope") == scope)
            and (scope_value is None or m.get("scope_value") == scope_value)
            and (is_active is None or bool(m.get("is_active", True)) == is_active)
        ]
    return wrap(state, AgentMemoryList(items=items, total=len(items)))


@router.patch("/agent/memory/{memory_id}", response_model=Envelope[MemorySchema])
def patch_memory(
    memory_id: str,
    body: AgentMemoryPatch,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[MemorySchema]:
    existing = state.sqlite.get_agent_memory(memory_id)
    if existing is None:
        raise not_found(f"教訓 {memory_id} は存在しません。")
    fields = body.model_dump(exclude_none=True)
    if "review_due_at" in fields and fields["review_due_at"] is not None:
        fields["review_due_at"] = fields["review_due_at"].isoformat()
    payload = to_dict(existing, json_fields=("derived_from",))
    payload.update(fields)
    payload["memory_id"] = memory_id
    updated = state.sqlite.upsert_agent_memory(**{
        k: payload[k]
        for k in payload
        if k not in {"id"}
    })
    seed = next(
        (m for m in state.payload.get("agent_memory") or [] if str(m.get("memory_id")) == memory_id),
        None,
    )
    return wrap(state, memory_from_row(updated, seed=seed))


@router.delete("/agent/memory/{memory_id}", response_model=Envelope[OkResponse])
def delete_memory(
    memory_id: str,
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[OkResponse]:
    if not state.sqlite.delete_agent_memory(memory_id):
        raise not_found(f"教訓 {memory_id} は存在しません。")
    return wrap(state, OkResponse(ok=True, id=memory_id))


@router.get("/agent/cost", response_model=Envelope[AgentCost])
def get_cost(
    period: str = Query(default="daily"),
    days: int = Query(default=30, ge=1, le=365),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[AgentCost]:
    raw = state.payload.get("llm_cost") or {}
    day_key = utc_now().date().isoformat()
    month_key = utc_now().strftime("%Y-%m")
    summary = state.sqlite.llm_cost_summary(day_key=day_key, month_key=month_key)
    settings = state.sqlite.get_settings_dict()
    by_tier = [
        CostByTier(
            tier=t["tier"],
            label_ja=t.get("label_ja"),
            model_id=t.get("model"),
            today_usd=float(t.get("today_usd") or 0.0),
        )
        for t in raw.get("by_tier") or []
    ]
    by_purpose = [
        CostByPurpose(
            purpose=p["purpose"],
            label_ja=p.get("label_ja"),
            today_usd=float(p.get("today_usd") or 0.0),
            share=p.get("share"),
            cache_hits=p.get("cache_hits"),
            cache_misses=p.get("cache_misses"),
        )
        for p in raw.get("by_purpose") or []
    ]
    recent = []
    for c in raw.get("recent_calls") or []:
        recent.append(
            LLMCall(
                at=as_utc_safe(c.get("at")),
                purpose=c.get("purpose") or "doc_summary",
                label_ja=c.get("label_ja"),
                model_id=str(c.get("model") or "unknown"),
                input_tokens=int(c.get("input_tokens") or 0),
                output_tokens=int(c.get("output_tokens") or 0),
                cost_usd=float(c.get("cost_usd") or 0.0),
                cache_hit=bool(c.get("cache_hit")),
                duration_sec=c.get("duration_sec"),
                status=c.get("status") or "success",
                error_ja=c.get("error_ja"),
            )
        )
    series = [CostDailyPoint.model_validate(p) for p in raw.get("daily_series") or []]
    return wrap(
        state,
        AgentCost(
            period=period,
            today_usd=float(raw.get("today_usd") or summary.get("spent_today_usd") or 0.0),
            daily_cap_usd=float(settings.get("llm.daily_cap_usd") or raw.get("daily_cap_usd") or 1.0),
            month_usd=float(raw.get("month_usd") or summary.get("spent_month_usd") or 0.0),
            monthly_cap_usd=float(settings.get("llm.monthly_cap_usd") or raw.get("monthly_cap_usd") or 20.0),
            projected_month_usd=raw.get("projected_month_usd"),
            kill_switch=bool(settings.get("llm.kill_switch") or raw.get("kill_switch")),
            by_tier=by_tier,
            by_purpose=by_purpose,
            recent_calls=recent,
            daily_series=series,
        ),
    )


def as_utc_safe(value):
    from services.api.util import as_utc

    return as_utc(value) or utc_now()


@router.get("/agent/critic-stats", response_model=Envelope[CriticStats])
def get_critic_stats(
    days: int = Query(default=30, ge=1, le=365),
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> Envelope[CriticStats]:
    raw = state.payload.get("critic_stats") or {}
    if raw:
        return wrap(
            state,
            CriticStats(
                days=int(raw.get("days") or days),
                n_reviewed=int(raw.get("n_reviewed") or 0),
                n_approved=int(raw.get("n_approved") or 0),
                n_revised=int(raw.get("n_revised") or 0),
                n_rejected=int(raw.get("n_rejected") or 0),
                rejection_rate=float(raw.get("rejection_rate") or 0.0),
                revision_rate=float(raw.get("revision_rate") or 0.0),
                reasons=[CriticReason.model_validate(r) for r in raw.get("reasons") or []],
                rate_trend=raw.get("rate_trend") or [],
            ),
        )
    recs = state.duck.get_recommendations(include_rejected=True, limit=1000)
    n = len(recs)
    n_rejected = sum(1 for r in recs if r.get("critic_verdict") == "rejected")
    n_revised = sum(1 for r in recs if r.get("critic_verdict") == "revised")
    n_approved = sum(1 for r in recs if r.get("critic_verdict") == "approved")
    return wrap(
        state,
        CriticStats(
            days=days,
            n_reviewed=n,
            n_approved=n_approved,
            n_revised=n_revised,
            n_rejected=n_rejected,
            rejection_rate=(n_rejected / n) if n else 0.0,
            revision_rate=(n_revised / n) if n else 0.0,
        ),
    )


@router.get("/agent/events")
async def agent_events(
    _user: User = Depends(require_user),
    state: AppState = Depends(get_app_state),
) -> EventSourceResponse:
    return EventSourceResponse(sse_iterator(state.bus), ping=15)
