"""エージェントジョブの共通型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class StepResult:
    status: str
    error: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    required: bool = False


@dataclass
class JobResult:
    job_name: str
    status: str
    market: str
    as_of: date
    run_id: int | None = None
    steps: dict[str, StepResult] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    recs: list[dict[str, Any]] = field(default_factory=list)
    outcomes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class PipelineResult:
    status: str
    market: str
    as_of: date
    jobs: dict[str, JobResult] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
