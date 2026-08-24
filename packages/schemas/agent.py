"""エージェント（docs/09-api-spec.md §2.8, docs/08-agent-loop.md）。"""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import Field

from packages.schemas.common import SchemaModel
from packages.schemas.enums import (
    JobStatus,
    JobTrigger,
    LLMPurpose,
    LLMTier,
    MemoryCategory,
    MemoryScope,
    Severity,
)


class JobPhase(SchemaModel):
    name: str
    label_ja: str | None = None
    status: str
    duration_sec: float | None = None
    detail_ja: str | None = None


class JobCheckpoint(SchemaModel):
    phase: str | None = None
    cursor: str | None = None
    completed: int | None = None
    total: int | None = None
    extra: dict[str, Any] | None = None


class JobRun(SchemaModel):
    job_run_id: int
    job_name: str
    label_ja: str | None = None
    market: str | None = None
    trigger: JobTrigger
    status: JobStatus
    attempt: int = 1
    started_at: dt.datetime
    finished_at: dt.datetime | None = None
    duration_sec: float | None = None
    output_summary_ja: str | None = None
    failed_steps: list[str] = Field(default_factory=list)
    phases: list[JobPhase] = Field(default_factory=list)
    checkpoint: JobCheckpoint | None = None
    metrics: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    parent_run_id: int | None = None
    git_commit: str | None = None


class JobRunList(SchemaModel):
    items: list[JobRun]
    total: int


class AgentMemory(SchemaModel):
    """`agent_memory`（docs/03-data-model.md §3.2）。"""

    memory_id: str
    category: MemoryCategory
    label_ja: str | None = None
    scope: MemoryScope
    scope_value: str | None = None
    lesson_ja: str
    evidence_ja: str
    derived_from: list[str] = Field(default_factory=list)
    n_observations: int
    confidence: float
    hit_rate_before: float | None = None
    hit_rate_after: float | None = None
    times_injected_30d: int | None = None
    effect_hit_rate_used: float | None = None
    effect_n_used: int | None = None
    effect_hit_rate_unused: float | None = None
    effect_n_unused: int | None = None
    is_active: bool = True
    # 有害な教訓（適用後の的中率が下がっている）を UI で明示する。
    harmful_flag: bool = False
    harmful_note_ja: str | None = None
    superseded_by: str | None = None
    created_at: dt.datetime | dt.date | None = None
    updated_at: dt.datetime | dt.date | None = None
    last_used_at: dt.datetime | dt.date | None = None
    use_count: int = 0
    review_due_at: dt.datetime | dt.date | None = None


class AgentMemoryList(SchemaModel):
    items: list[AgentMemory]
    total: int


class AgentMemoryPatch(SchemaModel):
    is_active: bool | None = None
    lesson_ja: str | None = None
    evidence_ja: str | None = None
    confidence: float | None = None
    review_due_at: dt.date | None = None


class CostByTier(SchemaModel):
    tier: LLMTier
    label_ja: str | None = None
    model_id: str | None = None
    today_usd: float = 0.0
    month_usd: float | None = None


class CostByPurpose(SchemaModel):
    purpose: LLMPurpose
    label_ja: str | None = None
    today_usd: float = 0.0
    month_usd: float | None = None
    share: float | None = None
    cache_hits: int | None = None
    cache_misses: int | None = None


class LLMCall(SchemaModel):
    at: dt.datetime
    purpose: LLMPurpose
    label_ja: str | None = None
    model_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    cache_hit: bool = False
    duration_sec: float | None = None
    status: str = "success"
    error_ja: str | None = None


class CostDailyPoint(SchemaModel):
    date: dt.date
    bulk: float = 0.0
    default: float = 0.0
    deep: float = 0.0
    embedding: float = 0.0


class AgentCost(SchemaModel):
    period: str
    today_usd: float
    daily_cap_usd: float
    month_usd: float
    monthly_cap_usd: float
    projected_month_usd: float | None = None
    kill_switch: bool = False
    by_tier: list[CostByTier] = Field(default_factory=list)
    by_purpose: list[CostByPurpose] = Field(default_factory=list)
    recent_calls: list[LLMCall] = Field(default_factory=list)
    daily_series: list[CostDailyPoint] = Field(default_factory=list)


class CriticReason(SchemaModel):
    code: str
    label_ja: str | None = None
    count: int


class CriticRateTrendPoint(SchemaModel):
    week_start: dt.date
    rejection_rate: float


class CriticStats(SchemaModel):
    days: int
    n_reviewed: int
    n_approved: int
    n_revised: int
    n_rejected: int
    rejection_rate: float
    revision_rate: float
    reasons: list[CriticReason] = Field(default_factory=list)
    rate_trend: list[CriticRateTrendPoint] = Field(default_factory=list)


# --- SSE (docs/09-api-spec.md §2.8) -----------------------------------------


class JobProgressEvent(SchemaModel):
    job_run_id: int
    job_name: str
    phase: str | None = None
    completed: int | None = None
    total: int | None = None
    eta_sec: float | None = None


class JobFinishedEvent(SchemaModel):
    job_run_id: int
    status: JobStatus
    duration_sec: float | None = None
    failed_steps: list[str] = Field(default_factory=list)


class AlertEvent(SchemaModel):
    severity: Severity
    category: str
    title_ja: str
    alert_id: str | None = None


class HeartbeatEvent(SchemaModel):
    at: dt.datetime


__all__ = [
    "AgentCost",
    "AgentMemory",
    "AgentMemoryList",
    "AgentMemoryPatch",
    "AlertEvent",
    "CostByPurpose",
    "CostByTier",
    "CostDailyPoint",
    "CriticRateTrendPoint",
    "CriticReason",
    "CriticStats",
    "HeartbeatEvent",
    "JobCheckpoint",
    "JobFinishedEvent",
    "JobPhase",
    "JobProgressEvent",
    "JobRun",
    "JobRunList",
    "LLMCall",
]
